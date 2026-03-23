"""
tools.py — Các hành động (Tools) mà AI Agent được phép thực thi.

Mỗi tool nhận tham số rõ ràng và trả về string mô tả kết quả.
Agent sẽ chọn tool phù hợp dựa trên reasoning của Gemini.
"""

import subprocess
import logging
import requests
import docker
import os

logger = logging.getLogger(__name__)
_docker_client = None

# ── Configuration from environment variables ──────────────────
DEFAULT_CONTAINER = os.environ.get("TARGET_CONTAINER_NAME", "target-app")
DEFAULT_INTERFACE = os.environ.get("DEFAULT_NETWORK_INTERFACE", "eth0")
DEFAULT_RATE_LIMIT = os.environ.get("DEFAULT_RATE_LIMIT", "50/sec")
RATE_LIMIT_BURST = os.environ.get("RATE_LIMIT_BURST", "200")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")


def _get_docker():
    global _docker_client
    if _docker_client is None:
        _docker_client = docker.from_env()
    return _docker_client


# ── Tool 1: Lấy top process trong container ─────────────────
def get_top_processes(container_name: str = None) -> str:
    """
    Lấy danh sách top 5 process tốn CPU nhất trong container.
    Dùng khi: CPU cao, cần xác định process thủ phạm.
    """
    if container_name is None:
        container_name = DEFAULT_CONTAINER

    try:
        client = _get_docker()
        container = client.containers.get(container_name)

        # Method 1: Dùng docker top API
        top_result = container.top(ps_args="aux")
        if not top_result or "Processes" not in top_result:
            return f"Cannot get processes for {container_name}"

        processes = top_result["Processes"]
        titles = top_result["Titles"]

        # Tìm CPU column index
        try:
            cpu_idx = titles.index("%CPU")
        except ValueError:
            cpu_idx = 2  # fallback

        # Sort by CPU descending
        sorted_procs = sorted(processes, key=lambda x: float(x[cpu_idx]) if x[cpu_idx].replace('.','').isdigit() else 0, reverse=True)

        # Format output
        output_lines = [" ".join(titles)]
        for proc in sorted_procs[:5]:
            output_lines.append(" ".join(proc))

        result_str = "\n".join(output_lines)
        logger.info(f"[get_top_processes] {container_name}:\n{result_str}")
        return f"Top processes in {container_name}:\n{result_str}"
    except Exception as e:
        logger.error(f"[get_top_processes] Error: {e}")
        return f"ERROR: {e}"


# ── Tool 2: Kill process trong container ────────────────────
def kill_process(container_name: str = None, process_name: str = "stress-ng") -> str:
    """
    Kill process theo tên trong container.
    Dùng khi: xác định được process gây quá tải.
    """
    if container_name is None:
        container_name = DEFAULT_CONTAINER

    try:
        # Use docker restart as failsafe method
        client = _get_docker()
        container = client.containers.get(container_name)

        # For stress-ng, restart container is most reliable
        if "stress" in process_name.lower():
            container.restart(timeout=10)
            msg = f"Restarted {container_name} to kill all {process_name} processes"
            logger.info(f"[kill_process] {msg}")
            return msg

        # For other processes, try exec kill
        top_result = container.top(ps_args="aux")
        if not top_result or "Processes" not in top_result:
            return f"Cannot get processes for {container_name}"

        processes = top_result["Processes"]
        titles = top_result["Titles"]

        try:
            pid_idx = titles.index("PID")
            cmd_idx = titles.index("COMMAND")
        except ValueError:
            pid_idx = 1
            cmd_idx = -1

        killed_count = 0
        for proc in processes:
            if process_name in proc[cmd_idx]:
                pid = proc[pid_idx]
                try:
                    container.exec_run(f"kill -9 {pid}")
                    killed_count += 1
                    logger.info(f"[kill_process] Killed PID {pid} ({process_name})")
                except Exception as e:
                    logger.warning(f"[kill_process] Failed to kill PID {pid}: {e}")

        if killed_count > 0:
            msg = f"Killed {killed_count} process(es) matching '{process_name}'"
        else:
            msg = f"No process matching '{process_name}' found"

        logger.info(f"[kill_process] {msg}")
        return msg
    except Exception as e:
        logger.error(f"[kill_process] Error: {e}")
        return f"ERROR: {e}"


# ── Tool 3: Block IP bằng iptables ──────────────────────────
def block_ip(ip: str) -> str:
    """
    Thêm rule iptables block IP tấn công.
    Dùng khi: phát hiện DDoS từ IP cụ thể.
    LƯU Ý: cần chạy container với --cap-add=NET_ADMIN
    """
    try:
        result = subprocess.run(
            ["iptables", "-I", "INPUT", "1", "-s", ip, "-j", "DROP"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            msg = f"Blocked IP {ip} via iptables"
        else:
            msg = f"iptables failed (code {result.returncode}): {result.stderr.strip()}"
        logger.info(f"[block_ip] {msg}")
        return msg
    except Exception as e:
        logger.error(f"[block_ip] Error: {e}")
        return f"ERROR: {e}"


# ── Tool 4: Restart service (container) ─────────────────────
def restart_service(container_name: str = None) -> str:
    """
    Restart container để phục hồi service.
    Dùng khi: service crash, không responsive.
    """
    if container_name is None:
        container_name = DEFAULT_CONTAINER

    try:
        client = _get_docker()
        container = client.containers.get(container_name)
        container.restart(timeout=10)
        msg = f"Restarted container: {container_name}"
        logger.info(f"[restart_service] {msg}")
        return msg
    except Exception as e:
        logger.error(f"[restart_service] Error: {e}")
        return f"ERROR: {e}"


# ── Tool 5: Query Prometheus metrics ────────────────────────
def get_prometheus_metrics(query: str) -> str:
    """
    Query Prometheus để lấy metric thực tế tại thời điểm hiện tại.
    Dùng khi: cần context số liệu cụ thể trước khi quyết định.
    Ví dụ query: 'node_cpu_seconds_total', 'flask_http_requests_total'
    """
    try:
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=5
        )
        data = r.json()
        if data["status"] == "success":
            results = data["data"]["result"]
            if not results:
                return f"No data for query: {query}"
            # Trả về tối đa 3 kết quả đầu
            summary = []
            for item in results[:3]:
                metric = item.get("metric", {})
                value = item.get("value", [None, "N/A"])[1]
                summary.append(f"{metric} = {value}")
            return f"Prometheus [{query}]:\n" + "\n".join(summary)
        else:
            return f"Prometheus error: {data}"
    except Exception as e:
        logger.error(f"[get_prometheus_metrics] Error: {e}")
        return f"ERROR: {e}"


# ── Tool 6: Giảm tải bằng rate limit (iptables limit) ───────
def apply_rate_limit(interface: str = None, rate: str = None) -> str:
    """
    Áp dụng rate limit trên interface mạng để chặn flood.
    Dùng khi: DDoS nhưng không có IP cụ thể để block.
    """
    if interface is None:
        interface = DEFAULT_INTERFACE
    if rate is None:
        rate = DEFAULT_RATE_LIMIT

    try:
        result = subprocess.run(
            ["iptables", "-A", "INPUT", "-i", interface,
             "-p", "tcp", "--dport", "5000",
             "-m", "limit", f"--limit={rate}", f"--limit-burst={RATE_LIMIT_BURST}",
             "-j", "ACCEPT"],
            capture_output=True, text=True, timeout=10
        )
        msg = f"Rate limit {rate} on {interface}: code {result.returncode}"
        logger.info(f"[apply_rate_limit] {msg}")
        return msg
    except Exception as e:
        return f"ERROR: {e}"


# ── Tool 7: Check system load ──────────────────────────────
def check_system_load() -> str:
    """
    Kiểm tra system load average và processes có thể gây load cao.
    Dùng khi: system load cao, cần identify root cause.
    """
    try:
        # Query prometheus cho load average
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": "node_load1"},
            timeout=5
        )
        data = r.json()
        if data["status"] == "success" and data["data"]["result"]:
            load1 = float(data["data"]["result"][0]["value"][1])
        else:
            load1 = 0.0

        result = [f"System load average (1-min): {load1:.2f}"]

        # Analyze load level
        if load1 < 1.0:
            result.append("Status: NORMAL (load < 1.0)")
        elif load1 < 2.0:
            result.append("Status: MODERATE (1.0 <= load < 2.0)")
        elif load1 < 4.0:
            result.append("Status: HIGH (2.0 <= load < 4.0) - needs attention")
        else:
            result.append("Status: CRITICAL (load >= 4.0) - immediate action required")

        # Recommendations
        if load1 > 2.0:
            result.append("Recommended actions:")
            result.append("- Check for CPU-intensive processes")
            result.append("- Consider restarting high-load containers")
            result.append("- Monitor I/O wait and disk utilization")

        logger.info(f"[check_system_load] Load: {load1:.2f}")
        return "\n".join(result)
    except Exception as e:
        logger.error(f"[check_system_load] Error: {e}")
        return f"ERROR: {e}"


# ── Tool 8: Reduce system load ──────────────────────────────
def reduce_system_load() -> str:
    """
    Giảm system load bằng cách restart containers và clear caches.
    Dùng khi: system load quá cao cần emergency reduction.
    """
    try:
        actions = []

        # 1. Restart target containers that might cause high load
        client = _get_docker()
        target_containers = [DEFAULT_CONTAINER]

        for container_name in target_containers:
            try:
                container = client.containers.get(container_name)
                container.restart(timeout=10)
                actions.append(f"✅ Restarted {container_name}")
                logger.info(f"[reduce_system_load] Restarted {container_name}")
            except Exception as e:
                actions.append(f"❌ Failed to restart {container_name}: {e}")
                logger.warning(f"[reduce_system_load] Failed to restart {container_name}: {e}")

        # 2. Wait a moment for system to settle
        import time
        time.sleep(2)

        # 3. Check load after actions
        try:
            r = requests.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": "node_load1"},
                timeout=5
            )
            data = r.json()
            if data["status"] == "success" and data["data"]["result"]:
                new_load = float(data["data"]["result"][0]["value"][1])
                actions.append(f"Current load after actions: {new_load:.2f}")

        except Exception:
            actions.append("Could not verify load after actions")

        result = "System load reduction actions:\n" + "\n".join(actions)
        logger.info(f"[reduce_system_load] {result}")
        return result
    except Exception as e:
        logger.error(f"[reduce_system_load] Error: {e}")
        return f"ERROR: {e}"
TOOLS = {
    "get_top_processes":    get_top_processes,
    "kill_process":         kill_process,
    "block_ip":             block_ip,
    "restart_service":      restart_service,
    "get_prometheus_metrics": get_prometheus_metrics,
    "apply_rate_limit":     apply_rate_limit,
    "check_system_load":    check_system_load,
    "reduce_system_load":   reduce_system_load,
}

TOOLS_DESCRIPTION = f"""
Available tools (use exact names and correct parameters):
- get_top_processes(container_name): Xem top CPU process trong container (default: {DEFAULT_CONTAINER})
- kill_process(container_name, process_name): Kill process theo tên (default container: {DEFAULT_CONTAINER})
- block_ip(ip): Block IP tấn công bằng iptables
- restart_service(container_name): Restart container (default: {DEFAULT_CONTAINER})
- get_prometheus_metrics(query): Query Prometheus lấy số liệu thực tế
- apply_rate_limit(interface, rate): Rate limit traffic (default: interface="{DEFAULT_INTERFACE}", rate="{DEFAULT_RATE_LIMIT}")
- check_system_load(): Kiểm tra system load (NO parameters needed)
- reduce_system_load(): Giảm system load (NO parameters needed)

IMPORTANT: check_system_load() and reduce_system_load() take NO parameters!
"""
