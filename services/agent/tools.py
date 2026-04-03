"""
tools.py — Các hành động (Tools) mà AI Agent được phép thực thi.

Mỗi tool nhận tham số rõ ràng và trả về string mô tả kết quả.
Agent sẽ chọn tool phù hợp dựa trên reasoning của Gemini.
"""

import logging
import requests
import docker
import os
import time

logger = logging.getLogger(__name__)
_docker_client = None

# ── Configuration from environment variables ──────────────────
DEFAULT_CONTAINER = os.environ.get("TARGET_CONTAINER_NAME", "target-app")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://grafana:3000")
GRAFANA_TOKEN = os.environ.get("GRAFANA_TOKEN", "")


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


# ── Process name synonyms for better matching ──────────────────
PROCESS_SYNONYMS = {
    "stress": ["stress-ng", "stress-ng-cpu", "stress-ng-vm", "stress"],
    "stress-ng": ["stress-ng", "stress-ng-cpu", "stress-ng-vm", "stress"],
    "cpu-stress": ["stress-ng", "stress-ng-cpu", "stress"],
    "load": ["stress-ng", "stress-ng-cpu", "yes", "dd"],
    "target-app": ["python app.py", "app.py", "python", "flask"],
    "web": ["python app.py", "app.py", "gunicorn", "uwsgi"],
    "high-cpu": ["stress-ng", "stress-ng-cpu", "yes", "dd", "spin"]
}

def _get_process_patterns(process_name):
    """Get all possible process name patterns for matching."""
    patterns = [process_name.lower()]

    # Add synonyms if available
    for key, synonyms in PROCESS_SYNONYMS.items():
        if key.lower() in process_name.lower() or process_name.lower() in key.lower():
            patterns.extend([s.lower() for s in synonyms])

    return list(set(patterns))  # Remove duplicates

def _match_process(command, patterns):
    """Check if a process command matches any of the patterns."""
    command_lower = command.lower()
    return any(pattern in command_lower for pattern in patterns)

# ── Tool 2: Kill process trong container ────────────────────
def kill_process(container_name: str = None, process_name: str = "stress-ng") -> str:
    """
    Kill process theo tên trong container với intelligent matching.
    Dùng khi: xác định được process gây quá tải.
    Support synonyms: stress, stress-ng, cpu-stress, etc.
    """
    if container_name is None:
        container_name = DEFAULT_CONTAINER

    # Get process patterns for intelligent matching
    patterns = _get_process_patterns(process_name)
    logger.info(f"[kill_process] Looking for processes matching: {patterns}")

    try:
        # Use docker restart as failsafe method for stress-ng
        client = _get_docker()
        container = client.containers.get(container_name)

        # For stress-related processes, restart container is most reliable
        if any(stress_pattern in process_name.lower() for stress_pattern in ["stress", "cpu", "load"]):
            container.restart(timeout=10)
            msg = f"Restarted {container_name} to kill all stress processes ({process_name})"
            logger.info(f"[kill_process] {msg}")
            return msg

        # For other processes, try intelligent process matching
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
        matched_processes = []

        # Find processes that match our patterns
        for proc in processes:
            command = proc[cmd_idx] if cmd_idx >= 0 else ""
            if _match_process(command, patterns):
                matched_processes.append((proc[pid_idx], command))

        # Kill matched processes
        for pid, command in matched_processes:
            try:
                container.exec_run(f"kill -9 {pid}")
                killed_count += 1
                logger.info(f"[kill_process] Killed PID {pid} ({command})")
            except Exception as e:
                logger.warning(f"[kill_process] Failed to kill PID {pid}: {e}")

        if killed_count > 0:
            msg = f"Killed {killed_count} process(es) matching '{process_name}': {[cmd for _, cmd in matched_processes]}"
        else:
            msg = f"No process matching '{process_name}' (patterns: {patterns}) found"

        logger.info(f"[kill_process] {msg}")
        return msg
    except Exception as e:
        logger.error(f"[kill_process] Error: {e}")
        return f"ERROR: {e}"


# ── Tool 3: Restart service (container) ─────────────────────
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


# ── Tool 4: Query Prometheus metrics ────────────────────────
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


# ── Tool 9: Auto-analyze and kill high CPU processes ───────────
def auto_kill_cpu_stress(container_name: str = None, cpu_threshold: float = 50.0) -> str:
    """
    Multi-step workflow: Automatically analyze top processes and kill high CPU consumers.
    Dùng khi: CPU overload, cần tự động xử lý không cần manual intervention.
    """
    if container_name is None:
        container_name = DEFAULT_CONTAINER

    try:
        # Step 1: Get top processes
        processes_result = get_top_processes(container_name)

        if "ERROR:" in processes_result or "Cannot" in processes_result:
            return f"Cannot analyze processes: {processes_result}"

        # Step 2: Parse process information to find high CPU consumers
        lines = processes_result.split('\n')
        high_cpu_processes = []

        for line in lines[1:]:  # Skip header
            parts = line.split()
            if len(parts) >= 11:  # Ensure we have enough columns
                try:
                    cpu_usage = float(parts[2])  # %CPU column
                    command = " ".join(parts[10:])  # COMMAND column

                    if cpu_usage > cpu_threshold:
                        high_cpu_processes.append((cpu_usage, command, parts[1]))  # (cpu%, command, pid)
                except (ValueError, IndexError):
                    continue

        if not high_cpu_processes:
            return f"No processes using >{cpu_threshold}% CPU found in {container_name}"

        # Step 3: Auto-kill stress processes
        killed_processes = []
        for cpu_usage, command, pid in high_cpu_processes:
            # Check if it's a stress-related process
            if any(stress_keyword in command.lower() for stress_keyword in ["stress", "yes", "dd if=/dev/zero"]):
                # Extract process name for kill_process
                process_name = "stress-ng" if "stress" in command.lower() else command.split()[0]
                kill_result = kill_process(container_name, process_name)
                killed_processes.append(f"CPU {cpu_usage}%: {command} -> {kill_result}")

        if killed_processes:
            result = f"Auto-killed {len(killed_processes)} high CPU process(es):\n" + "\n".join(killed_processes)
        else:
            result = f"Found {len(high_cpu_processes)} high CPU processes but none were stress-related: {[cmd for _, cmd, _ in high_cpu_processes]}"

        logger.info(f"[auto_kill_cpu_stress] {result}")
        return result

    except Exception as e:
        logger.error(f"[auto_kill_cpu_stress] Error: {e}")
        return f"ERROR: {e}"


# ── Tool 10: Smart container validation ─────────────────────────
def validate_container_exists(container_name: str = None) -> str:
    """
    Validate that a container exists and is running before taking actions.
    Dùng khi: Cần check container trước khi thực hiện action để tránh lỗi.
    """
    if container_name is None:
        container_name = DEFAULT_CONTAINER

    try:
        client = _get_docker()
        container = client.containers.get(container_name)

        status = container.status
        if status == "running":
            return f"✅ Container '{container_name}' exists and is running"
        else:
            return f"⚠️ Container '{container_name}' exists but is {status}"

    except docker.errors.NotFound:
        return f"❌ Container '{container_name}' not found"
    except Exception as e:
        logger.error(f"[validate_container_exists] Error: {e}")
        return f"ERROR: {e}"


# ── Tool 11: Post Grafana annotation ────────────────────────
def post_grafana_annotation(text: str, tags: list) -> str:
    """
    Post an annotation to all Grafana dashboards marking AI intervention.
    Called automatically after every tool execution — failure is non-fatal.

    Args:
        text: annotation text, e.g. "🤖 restart_service — ddos | CPU:45% MEM:60%"
        tags: list of tag strings, e.g. ["aiops", "auto-remediation", "ddos"]

    Returns:
        str: "Annotation posted OK (200)" or "Annotation skipped (no token)" or "ERROR: ..."
    """
    if not GRAFANA_TOKEN:
        logger.warning("[post_grafana_annotation] GRAFANA_TOKEN not set — skipping annotation")
        return "Annotation skipped (no token)"

    try:
        response = requests.post(
            f"{GRAFANA_URL}/api/annotations",
            json={"text": text, "tags": tags},
            headers={
                "Authorization": f"Bearer {GRAFANA_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=5,
        )
        msg = f"Annotation posted OK ({response.status_code})"
        logger.info(f"[post_grafana_annotation] {msg}: {text[:80]}")
        return msg
    except Exception as e:
        msg = f"ERROR: {e}"
        logger.warning(f"[post_grafana_annotation] {msg}")
        return msg


TOOLS = {
    "get_top_processes":    get_top_processes,
    "kill_process":         kill_process,
    "restart_service":      restart_service,
    "check_system_load":    check_system_load,
    "reduce_system_load":   reduce_system_load,
    "auto_kill_cpu_stress": auto_kill_cpu_stress,
    # get_prometheus_metrics  — internal diagnostic utility, not AI-callable
    # post_grafana_annotation — called automatically by webhook(), not by LLM
    # validate_container_exists — internal guard, not AI-callable
}

TOOLS_DESCRIPTION = f"""
Available tools grouped by scenario (use ONLY the tools listed for the active scenario):

[scenario=cpu_stress] CPU / process overload:
- auto_kill_cpu_stress(container_name, cpu_threshold): Multi-step workflow to auto-kill high-CPU processes (preferred)
- get_top_processes(container_name): Inspect top CPU processes in container (default: {DEFAULT_CONTAINER})
- kill_process(container_name, process_name): Kill a named process (default container: {DEFAULT_CONTAINER})

[scenario=ddos] Network / request rate attack:
- restart_service(container_name): Restart the target container to recover from flood (default: {DEFAULT_CONTAINER})

[scenario=memory_stress] Memory exhaustion:
- restart_service(container_name): Restart container to free memory (default: {DEFAULT_CONTAINER})
- reduce_system_load(): Emergency load reduction — restarts containers and clears state (NO parameters)

[scenario=system_load] High system load average:
- reduce_system_load(): Reduce system load — restarts containers and clears state (NO parameters)
- check_system_load(): Read current load metrics (NO parameters)

[diagnostic] Query Prometheus for additional context before acting (any scenario):
- get_prometheus_metrics(query): Run a raw PromQL query and return current value — use to confirm severity or check related metrics

NOTE: post_grafana_annotation is called automatically — do NOT include it in your action response.
CRITICAL: reduce_system_load() and check_system_load() take NO parameters — params must be {{}}.
"""
