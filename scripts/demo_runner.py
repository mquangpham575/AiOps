"""
demo_runner.py — Automated AIOps demo scenario runner with MTTR measurement.

Usage:
    python demo_runner.py --scenario all              # run DDoS + CPU + Memory in sequence
    python demo_runner.py --scenario ddos             # run single scenario
    python demo_runner.py --scenario cpu
    python demo_runner.py --scenario memory
    python demo_runner.py --export results.csv        # output file (default: results.csv)
    python demo_runner.py --cooldown 60               # seconds between scenarios (default: 90)
"""

import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

from dotenv import load_dotenv
load_dotenv()

# ── Configuration ────────────────────────────────────────────
_azure_ip = os.environ.get("AZURE_VM_IP")
_default_target = f"http://{_azure_ip}:80" if _azure_ip else "http://localhost:5000"

TARGET_URL     = os.environ.get("TARGET_URL",     _default_target)
AGENT_URL      = os.environ.get("AGENT_URL",      "http://localhost:8080")
PROMETHEUS_URL = "http://localhost:9090"
AGENT_KEY      = os.environ.get("AGENT_API_KEY",  "")

SCENARIO_TIMEOUT_S = 180
POLL_INTERVAL_S    = 2
PROM_POLL_S        = 3


class DemoRunner:
    def __init__(
        self,
        target_url: str = TARGET_URL,
        agent_url: str = AGENT_URL,
        prometheus_url: str = PROMETHEUS_URL,
        agent_key: str = AGENT_KEY,
        export_file: str = "results.csv",
        cooldown: int = 90,
    ):
        self.target_url     = target_url
        self.agent_url      = agent_url
        self.prometheus_url = prometheus_url
        self.agent_key      = agent_key
        self.export_file    = export_file
        self.cooldown       = cooldown
        self.results: list[dict] = []

    # ── Utilities ──────────────────────────────────────────────

    def _prom_query(self, query: str, default: float = 0.0) -> float:
        """Run a Prometheus instant query; return float or default on failure."""
        try:
            r = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query},
                timeout=5,
            )
            data = r.json()
            if data["status"] == "success" and data["data"]["result"]:
                return float(data["data"]["result"][0]["value"][1])
        except Exception:
            pass
        return default

    def _agent_headers(self) -> dict:
        return {"X-Agent-Key": self.agent_key}

    def preflight(self) -> bool:
        """Check all required services are reachable. Returns True if all healthy."""
        checks = [
            (f"{self.target_url}/health",     "target-app"),
            (f"{self.agent_url}/health",       "agent"),
            (f"{self.prometheus_url}/-/ready", "prometheus"),
        ]
        all_ok = True
        for url, name in checks:
            try:
                r = requests.get(url, timeout=5)
                icon = "✅" if r.status_code == 200 else "❌"
                print(f"  {icon} {name:15s} {url}")
                if r.status_code != 200:
                    all_ok = False
            except Exception as e:
                print(f"  ❌ {name:15s} UNREACHABLE: {e}")
                all_ok = False
        return all_ok

    def record_baseline(self) -> dict:
        """Snapshot current CPU%, memory%, and latency from Prometheus."""
        cpu_pct     = self._prom_query(
            "100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)"
        )
        memory_pct  = self._prom_query(
            "(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100"
        )
        latency_raw = self._prom_query(
            "rate(flask_http_request_duration_seconds_sum{job='target-app'}[1m]) / rate(flask_http_request_duration_seconds_count{job='target-app'}[1m])",
            default=0.0,
        )
        return {
            "cpu_pct":    round(cpu_pct, 1),
            "memory_pct": round(memory_pct, 1),
            "latency_ms": round(latency_raw * 1000, 1),
        }

    def find_agent_action(self, after: datetime, scenario: str) -> dict | None:
        """
        Poll agent /logs for the most recent entry with matching scenario after `after`.
        Returns the log entry dict or None.
        """
        try:
            r = requests.get(
                f"{self.agent_url}/logs",
                headers=self._agent_headers(),
                timeout=5,
            )
            logs = r.json()
            for entry in reversed(logs):
                ts_str = entry.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts > after and entry.get("scenario") == scenario and entry.get("action"):
                        return entry
                except ValueError:
                    continue
        except Exception:
            pass
        return None

    def wait_for_alert_fired(self, alert_names: list[str], after: datetime) -> datetime | None:
        """
        Poll Prometheus /api/v1/alerts until one of alert_names is in firing state
        with activeAt > after. Returns the activeAt datetime or None on timeout.
        """
        deadline = time.time() + SCENARIO_TIMEOUT_S
        while time.time() < deadline:
            try:
                r = requests.get(
                    f"{self.prometheus_url}/api/v1/alerts",
                    timeout=5,
                )
                data = r.json()
                for alert in data.get("data", {}).get("alerts", []):
                    if (
                        alert.get("labels", {}).get("alertname") in alert_names
                        and alert.get("state") == "firing"
                    ):
                        active_at_str = alert.get("activeAt", "")
                        try:
                            active_at = datetime.fromisoformat(
                                active_at_str.replace("Z", "+00:00")
                            )
                            if active_at > after:
                                return active_at
                        except ValueError:
                            pass
            except Exception:
                pass
            time.sleep(PROM_POLL_S)
        return None

    def wait_for_recovery(
        self,
        query: str,
        threshold: float,
        below: bool = True,
        consecutive_required: int = 3,
    ) -> datetime | None:
        """
        Poll Prometheus until metric stays on the recovery side of threshold for
        `consecutive_required` polls in a row. Times out after SCENARIO_TIMEOUT_S.
        Requiring consecutive polls prevents false-positive recovery on transient dips.
        """
        deadline = time.time() + SCENARIO_TIMEOUT_S
        consecutive = 0
        while time.time() < deadline:
            value = self._prom_query(query)
            if (below and value < threshold) or (not below and value > threshold):
                consecutive += 1
                if consecutive >= consecutive_required:
                    return datetime.now(timezone.utc)
            else:
                consecutive = 0
            time.sleep(PROM_POLL_S)
        return None

    def export_csv(self):
        """Write self.results to the export CSV file."""
        if not self.results:
            print("No results to export.")
            return
        fieldnames = [
            "scenario",
            "t0_attack_start", "alert_fired_at", "agent_acted_at", "recovered_at",
            "detection_latency_s", "response_latency_s", "remediation_s", "mttr_s",
            "action", "confidence", "llm_latency_s",
            "baseline_cpu_pct", "peak_cpu_pct",
            "peak_req_per_sec",
            "baseline_mem_pct", "peak_mem_pct",
        ]
        with open(self.export_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.results)
        print(f"\n📊 Results exported to {self.export_file}")

    def print_summary(self):
        """Print a results table to stdout."""
        if not self.results:
            return
        print("\n" + "─" * 80)
        print(f"{'Scenario':<18} {'Action':<26} {'Detect':>7} {'Respond':>8} {'Remediate':>10} {'MTTR':>8}  {'Status'}")
        print("─" * 80)
        for r in self.results:
            mttr    = f"{r['mttr_s']}s"   if r.get("mttr_s")               else "TIMEOUT"
            detect  = f"{r['detection_latency_s']}s" if r.get("detection_latency_s") else "—"
            respond = f"{r['response_latency_s']}s"  if r.get("response_latency_s")  else "—"
            remedia = f"{r['remediation_s']}s"        if r.get("remediation_s")        else "—"
            status  = "✅" if r.get("mttr_s") else "❌"
            print(f"{r['scenario']:<18} {str(r.get('action','—')):<26} {detect:>7} {respond:>8} {remedia:>10} {mttr:>8}  {status}")
        print("─" * 80)

    # ── Scenarios ──────────────────────────────────────────────

    def run_ddos(self) -> dict:
        """Scenario 2: DDoS simulation via Locust with staged load shape."""
        print("\n── Scenario 2: DDoS ──────────────────────────────────────")
        t0 = datetime.now(timezone.utc)
        baseline = self.record_baseline()
        print(f"  Baseline: CPU={baseline['cpu_pct']}% MEM={baseline['memory_pct']}% LAT={baseline['latency_ms']}ms")

        # StagedLoadShape overrides --users/--spawn-rate; pass profile via env
        env = {**os.environ, "ATTACK_PROFILE": "ddos"}
        proc = subprocess.Popen([
            sys.executable, "-m", "locust",
            "-f", "loadtest/locustfile.py",
            f"--host={self.target_url}",
            "--run-time", "3m", "--headless", "--tags", "ddos",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)

        # T1: wait for Prometheus to fire the alert
        print("  ⏳ Waiting for alert to fire in Prometheus...")
        t1 = self.wait_for_alert_fired(
            ["HighRequestLatency", "HighRequestRate"], after=t0
        )
        if t1:
            print(f"  🔔 Alert fired   T1={t1.strftime('%H:%M:%S')}")
        else:
            print("  ⚠️  Alert not detected — continuing anyway")

        # T2: wait for agent to act
        agent_entry = None
        deadline = time.time() + SCENARIO_TIMEOUT_S
        while time.time() < deadline:
            agent_entry = self.find_agent_action(after=t0, scenario="ddos")
            if agent_entry:
                print(f"  🤖 Agent acted   T2={agent_entry['timestamp'][11:19]}  action={agent_entry['action']}")
                break
            time.sleep(POLL_INTERVAL_S)

        # T3: wait for sustained recovery
        t3 = self.wait_for_recovery(
            "rate(flask_http_request_duration_seconds_sum{job='target-app'}[1m])"
            " / rate(flask_http_request_duration_seconds_count{job='target-app'}[1m]) * 1000",
            threshold=1000.0,
        )

        proc.terminate()
        proc.wait(timeout=10)

        # Derive T2 datetime from agent log entry
        t2 = None
        if agent_entry and agent_entry.get("timestamp"):
            try:
                t2 = datetime.fromisoformat(agent_entry["timestamp"].replace("Z", "+00:00"))
            except ValueError:
                pass

        detection_latency_s = round((t1 - t0).total_seconds(), 1) if t1 else None
        response_latency_s  = round((t2 - t1).total_seconds(), 1) if (t2 and t1) else None
        remediation_s       = round((t3 - t2).total_seconds(), 1) if (t3 and t2) else None
        mttr_s              = round((t3 - t0).total_seconds(), 1) if t3 else None

        if mttr_s:
            print(f"  ✅ Recovered. MTTR={mttr_s}s  "
                  f"(detect={detection_latency_s}s respond={response_latency_s}s remediate={remediation_s}s)")
        else:
            print("  ❌ TIMEOUT — recovery not detected within 3 minutes")

        peak_req_per_sec = round(
            self._prom_query("rate(flask_http_requests_total{job='target-app'}[1m])"), 1
        )

        return {
            "scenario":             "ddos",
            "t0_attack_start":      t0.strftime("%H:%M:%S"),
            "alert_fired_at":       t1.strftime("%H:%M:%S") if t1 else "",
            "agent_acted_at":       (agent_entry.get("timestamp") or "")[:19] if agent_entry else "",
            "recovered_at":         t3.strftime("%H:%M:%S") if t3 else "TIMEOUT",
            "detection_latency_s":  detection_latency_s,
            "response_latency_s":   response_latency_s,
            "remediation_s":        remediation_s,
            "mttr_s":               mttr_s,
            "action":               agent_entry.get("action") if agent_entry else None,
            "confidence":           agent_entry.get("confidence") if agent_entry else None,
            "llm_latency_s":        agent_entry.get("llm_latency_s") if agent_entry else None,
            "baseline_cpu_pct":     baseline["cpu_pct"],
            "peak_cpu_pct":         round(self._prom_query("100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)"), 1),
            "peak_req_per_sec":     peak_req_per_sec,
            "baseline_mem_pct":     baseline["memory_pct"],
            "peak_mem_pct":         round(self._prom_query("(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100"), 1),
        }

    def run_cpu(self) -> dict:
        """Scenario 3: CPU stress via stress-ng inside target-app container."""
        print("\n── Scenario 3: CPU Stress ─────────────────────────────────")
        t0 = datetime.now(timezone.utc)
        baseline = self.record_baseline()
        print(f"  Baseline: CPU={baseline['cpu_pct']}% MEM={baseline['memory_pct']}%")

        env = {**os.environ}
        if _azure_ip:
            env["DOCKER_HOST"] = f"tcp://{_azure_ip}:2375"

        proc = subprocess.Popen([
            "docker", "exec", "target-app",
            "stress-ng", "--cpu", "4", "--timeout", "90s",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)

        # T1: wait for Prometheus alert
        print("  ⏳ Waiting for alert to fire in Prometheus...")
        t1 = self.wait_for_alert_fired(
            ["ContainerHighCPU", "HighCPUUsage", "CriticalCPUStress"], after=t0
        )
        if t1:
            print(f"  🔔 Alert fired   T1={t1.strftime('%H:%M:%S')}")
        else:
            print("  ⚠️  Alert not detected — continuing anyway")

        # T2: wait for agent to act
        agent_entry = None
        deadline = time.time() + SCENARIO_TIMEOUT_S
        while time.time() < deadline:
            agent_entry = self.find_agent_action(after=t0, scenario="cpu_stress")
            if agent_entry:
                print(f"  🤖 Agent acted   T2={agent_entry['timestamp'][11:19]}  action={agent_entry['action']}")
                break
            time.sleep(POLL_INTERVAL_S)

        # T3: sustained recovery
        t3 = self.wait_for_recovery(
            "100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)",
            threshold=30.0,
        )

        proc.terminate()
        proc.wait(timeout=5)

        t2 = None
        if agent_entry and agent_entry.get("timestamp"):
            try:
                t2 = datetime.fromisoformat(agent_entry["timestamp"].replace("Z", "+00:00"))
            except ValueError:
                pass

        detection_latency_s = round((t1 - t0).total_seconds(), 1) if t1 else None
        response_latency_s  = round((t2 - t1).total_seconds(), 1) if (t2 and t1) else None
        remediation_s       = round((t3 - t2).total_seconds(), 1) if (t3 and t2) else None
        mttr_s              = round((t3 - t0).total_seconds(), 1) if t3 else None

        if mttr_s:
            print(f"  ✅ Recovered. MTTR={mttr_s}s  "
                  f"(detect={detection_latency_s}s respond={response_latency_s}s remediate={remediation_s}s)")
        else:
            print("  ❌ TIMEOUT")

        return {
            "scenario":             "cpu_stress",
            "t0_attack_start":      t0.strftime("%H:%M:%S"),
            "alert_fired_at":       t1.strftime("%H:%M:%S") if t1 else "",
            "agent_acted_at":       (agent_entry.get("timestamp") or "")[:19] if agent_entry else "",
            "recovered_at":         t3.strftime("%H:%M:%S") if t3 else "TIMEOUT",
            "detection_latency_s":  detection_latency_s,
            "response_latency_s":   response_latency_s,
            "remediation_s":        remediation_s,
            "mttr_s":               mttr_s,
            "action":               agent_entry.get("action") if agent_entry else None,
            "confidence":           agent_entry.get("confidence") if agent_entry else None,
            "llm_latency_s":        agent_entry.get("llm_latency_s") if agent_entry else None,
            "baseline_cpu_pct":     baseline["cpu_pct"],
            "peak_cpu_pct":         round(self._prom_query("100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)"), 1),
            "peak_req_per_sec":     None,
            "baseline_mem_pct":     baseline["memory_pct"],
            "peak_mem_pct":         round(self._prom_query("(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100"), 1),
        }

    def run_memory(self) -> dict:
        """Scenario 4: Memory exhaustion via Locust with staged load shape."""
        print("\n── Scenario 4: Memory Exhaustion ──────────────────────────")
        t0 = datetime.now(timezone.utc)
        baseline = self.record_baseline()
        print(f"  Baseline: CPU={baseline['cpu_pct']}% MEM={baseline['memory_pct']}%")

        # StagedLoadShape overrides --users/--spawn-rate; pass profile via env
        env = {**os.environ, "ATTACK_PROFILE": "memory"}
        proc = subprocess.Popen([
            sys.executable, "-m", "locust",
            "-f", "loadtest/locustfile.py",
            f"--host={self.target_url}",
            "--run-time", "3m", "--headless", "--tags", "memory",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)

        # T1: wait for Prometheus alert
        print("  ⏳ Waiting for alert to fire in Prometheus...")
        t1 = self.wait_for_alert_fired(["HighMemoryUsage"], after=t0)
        if t1:
            print(f"  🔔 Alert fired   T1={t1.strftime('%H:%M:%S')}")
        else:
            print("  ⚠️  Alert not detected — continuing anyway")

        # T2: wait for agent to act
        agent_entry = None
        deadline = time.time() + SCENARIO_TIMEOUT_S
        while time.time() < deadline:
            agent_entry = self.find_agent_action(after=t0, scenario="memory_stress")
            if agent_entry:
                print(f"  🤖 Agent acted   T2={agent_entry['timestamp'][11:19]}  action={agent_entry['action']}")
                break
            time.sleep(POLL_INTERVAL_S)

        # T3: sustained recovery
        t3 = self.wait_for_recovery(
            "(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100",
            threshold=60.0,
        )

        proc.terminate()
        proc.wait(timeout=5)

        t2 = None
        if agent_entry and agent_entry.get("timestamp"):
            try:
                t2 = datetime.fromisoformat(agent_entry["timestamp"].replace("Z", "+00:00"))
            except ValueError:
                pass

        detection_latency_s = round((t1 - t0).total_seconds(), 1) if t1 else None
        response_latency_s  = round((t2 - t1).total_seconds(), 1) if (t2 and t1) else None
        remediation_s       = round((t3 - t2).total_seconds(), 1) if (t3 and t2) else None
        mttr_s              = round((t3 - t0).total_seconds(), 1) if t3 else None

        if mttr_s:
            print(f"  ✅ Recovered. MTTR={mttr_s}s  "
                  f"(detect={detection_latency_s}s respond={response_latency_s}s remediate={remediation_s}s)")
        else:
            print("  ❌ TIMEOUT")

        return {
            "scenario":             "memory_stress",
            "t0_attack_start":      t0.strftime("%H:%M:%S"),
            "alert_fired_at":       t1.strftime("%H:%M:%S") if t1 else "",
            "agent_acted_at":       (agent_entry.get("timestamp") or "")[:19] if agent_entry else "",
            "recovered_at":         t3.strftime("%H:%M:%S") if t3 else "TIMEOUT",
            "detection_latency_s":  detection_latency_s,
            "response_latency_s":   response_latency_s,
            "remediation_s":        remediation_s,
            "mttr_s":               mttr_s,
            "action":               agent_entry.get("action") if agent_entry else None,
            "confidence":           agent_entry.get("confidence") if agent_entry else None,
            "llm_latency_s":        agent_entry.get("llm_latency_s") if agent_entry else None,
            "baseline_cpu_pct":     baseline["cpu_pct"],
            "peak_cpu_pct":         round(self._prom_query("100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)"), 1),
            "peak_req_per_sec":     None,
            "baseline_mem_pct":     baseline["memory_pct"],
            "peak_mem_pct":         round(self._prom_query("(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100"), 1),
        }

    def run(self, scenario: str = "all"):
        """Run the specified scenario(s) and export results."""
        print("=" * 60)
        print("  AIOps Demo Runner")
        print("=" * 60)
        print("\n── Pre-flight checks ──────────────────────────────────")
        if not self.preflight():
            print("\n❌ Pre-flight failed — ensure docker-compose is up.")
            sys.exit(1)
        print("  All services healthy.\n")

        runners = {
            "all":    [self.run_ddos, self.run_cpu, self.run_memory],
            "ddos":   [self.run_ddos],
            "cpu":    [self.run_cpu],
            "memory": [self.run_memory],
        }.get(scenario, [self.run_ddos])

        for i, fn in enumerate(runners):
            result = fn()
            self.results.append(result)
            if i < len(runners) - 1:
                print(f"\n  Cooling down {self.cooldown}s before next scenario...")
                time.sleep(self.cooldown)

        self.print_summary()
        self.export_csv()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOps Demo Runner")
    parser.add_argument("--scenario", default="all",
                        choices=["all", "ddos", "cpu", "memory"])
    parser.add_argument("--export", default="results.csv")
    parser.add_argument("--cooldown", type=int, default=90)
    args = parser.parse_args()

    runner = DemoRunner(export_file=args.export, cooldown=args.cooldown)
    runner.run(scenario=args.scenario)
