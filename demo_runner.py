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

# ── Configuration ────────────────────────────────────────────
TARGET_URL     = os.environ.get("TARGET_URL",     "http://localhost:5000")
AGENT_URL      = os.environ.get("AGENT_URL",      "http://localhost:8080")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
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

    def wait_for_recovery(self, query: str, threshold: float, below: bool = True) -> datetime | None:
        """Poll Prometheus until metric crosses threshold. Times out after SCENARIO_TIMEOUT_S."""
        deadline = time.time() + SCENARIO_TIMEOUT_S
        while time.time() < deadline:
            value = self._prom_query(query)
            if (below and value < threshold) or (not below and value > threshold):
                return datetime.now(timezone.utc)
            time.sleep(PROM_POLL_S)
        return None

    def export_csv(self):
        """Write self.results to the export CSV file."""
        if not self.results:
            print("No results to export.")
            return
        fieldnames = [
            "scenario", "alert_fired_at", "agent_acted_at", "recovered_at",
            "mttr_s", "action", "confidence", "llm_latency_s",
            "baseline_cpu_pct", "peak_cpu_pct", "baseline_mem_pct", "peak_mem_pct",
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
        print("\n" + "─" * 70)
        print(f"{'Scenario':<18} {'Action':<26} {'MTTR':>8}  {'Status'}")
        print("─" * 70)
        for r in self.results:
            mttr = f"{r['mttr_s']}s" if r.get("mttr_s") else "TIMEOUT"
            status = "✅" if r.get("mttr_s") else "❌"
            print(f"{r['scenario']:<18} {str(r.get('action','—')):<26} {mttr:>8}  {status}")
        print("─" * 70)

    # ── Scenarios ──────────────────────────────────────────────

    def run_ddos(self) -> dict:
        """Scenario 2: DDoS simulation via Locust."""
        print("\n── Scenario 2: DDoS ──────────────────────────────────────")
        t_start  = datetime.now(timezone.utc)
        baseline = self.record_baseline()
        print(f"  Baseline: CPU={baseline['cpu_pct']}% MEM={baseline['memory_pct']}% LAT={baseline['latency_ms']}ms")

        proc = subprocess.Popen([
            sys.executable, "-m", "locust",
            "-f", "loadtest/locustfile.py",
            f"--host={self.target_url}",
            "--users", "500", "--spawn-rate", "50",
            "--run-time", "3m", "--headless", "--tags", "ddos",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        agent_entry = None
        deadline = time.time() + SCENARIO_TIMEOUT_S
        while time.time() < deadline:
            agent_entry = self.find_agent_action(after=t_start, scenario="ddos")
            if agent_entry:
                print(f"  🤖 Agent acted: {agent_entry['action']}")
                break
            time.sleep(POLL_INTERVAL_S)

        recovered_at = self.wait_for_recovery(
            "rate(flask_http_request_duration_seconds_sum{job='target-app'}[1m]) / rate(flask_http_request_duration_seconds_count{job='target-app'}[1m]) * 1000",
            threshold=1000.0,
        )

        proc.terminate()
        proc.wait(timeout=10)

        mttr_s = round((recovered_at - t_start).total_seconds(), 1) if recovered_at else None
        if mttr_s:
            print(f"  ✅ Recovered. MTTR = {mttr_s}s")
        else:
            print("  ❌ TIMEOUT — recovery not detected within 3 minutes")

        return {
            "scenario":          "ddos",
            "alert_fired_at":    t_start.strftime("%H:%M:%S"),
            "agent_acted_at":    (agent_entry.get("timestamp") or "")[:19] if agent_entry else "",
            "recovered_at":      recovered_at.strftime("%H:%M:%S") if recovered_at else "TIMEOUT",
            "mttr_s":            mttr_s,
            "action":            agent_entry.get("action") if agent_entry else None,
            "confidence":        agent_entry.get("confidence") if agent_entry else None,
            "llm_latency_s":     agent_entry.get("llm_latency_s") if agent_entry else None,
            "baseline_cpu_pct":  baseline["cpu_pct"],
            "peak_cpu_pct":      round(self._prom_query("100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)"), 1),
            "baseline_mem_pct":  baseline["memory_pct"],
            "peak_mem_pct":      round(self._prom_query("(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100"), 1),
        }

    def run_cpu(self) -> dict:
        """Scenario 3: CPU stress via stress-ng inside target-app container."""
        print("\n── Scenario 3: CPU Stress ─────────────────────────────────")
        t_start  = datetime.now(timezone.utc)
        baseline = self.record_baseline()
        print(f"  Baseline: CPU={baseline['cpu_pct']}% MEM={baseline['memory_pct']}%")

        proc = subprocess.Popen([
            "docker", "exec", "target-app",
            "stress-ng", "--cpu", "4", "--timeout", "90s",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        agent_entry = None
        deadline = time.time() + SCENARIO_TIMEOUT_S
        while time.time() < deadline:
            agent_entry = self.find_agent_action(after=t_start, scenario="cpu_stress")
            if agent_entry:
                print(f"  🤖 Agent acted: {agent_entry['action']}")
                break
            time.sleep(POLL_INTERVAL_S)

        recovered_at = self.wait_for_recovery(
            "100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)",
            threshold=30.0,
        )

        proc.terminate()
        proc.wait(timeout=5)

        mttr_s = round((recovered_at - t_start).total_seconds(), 1) if recovered_at else None
        if mttr_s:
            print(f"  ✅ Recovered. MTTR = {mttr_s}s")
        else:
            print("  ❌ TIMEOUT")

        return {
            "scenario":          "cpu_stress",
            "alert_fired_at":    t_start.strftime("%H:%M:%S"),
            "agent_acted_at":    (agent_entry.get("timestamp") or "")[:19] if agent_entry else "",
            "recovered_at":      recovered_at.strftime("%H:%M:%S") if recovered_at else "TIMEOUT",
            "mttr_s":            mttr_s,
            "action":            agent_entry.get("action") if agent_entry else None,
            "confidence":        agent_entry.get("confidence") if agent_entry else None,
            "llm_latency_s":     agent_entry.get("llm_latency_s") if agent_entry else None,
            "baseline_cpu_pct":  baseline["cpu_pct"],
            "peak_cpu_pct":      round(self._prom_query("100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)"), 1),
            "baseline_mem_pct":  baseline["memory_pct"],
            "peak_mem_pct":      round(self._prom_query("(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100"), 1),
        }

    def run_memory(self) -> dict:
        """Scenario 4: Memory exhaustion via Locust MemoryStressUser."""
        print("\n── Scenario 4: Memory Exhaustion ──────────────────────────")
        t_start  = datetime.now(timezone.utc)
        baseline = self.record_baseline()
        print(f"  Baseline: CPU={baseline['cpu_pct']}% MEM={baseline['memory_pct']}%")

        proc = subprocess.Popen([
            sys.executable, "-m", "locust",
            "-f", "loadtest/locustfile.py",
            f"--host={self.target_url}",
            "--users", "20", "--spawn-rate", "5",
            "--run-time", "3m", "--headless", "--tags", "memory",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        agent_entry = None
        deadline = time.time() + SCENARIO_TIMEOUT_S
        while time.time() < deadline:
            agent_entry = self.find_agent_action(after=t_start, scenario="memory_stress")
            if agent_entry:
                print(f"  🤖 Agent acted: {agent_entry['action']}")
                break
            time.sleep(POLL_INTERVAL_S)

        recovered_at = self.wait_for_recovery(
            "(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100",
            threshold=60.0,
        )

        proc.terminate()
        proc.wait(timeout=5)

        mttr_s = round((recovered_at - t_start).total_seconds(), 1) if recovered_at else None
        if mttr_s:
            print(f"  ✅ Recovered. MTTR = {mttr_s}s")
        else:
            print("  ❌ TIMEOUT")

        return {
            "scenario":          "memory_stress",
            "alert_fired_at":    t_start.strftime("%H:%M:%S"),
            "agent_acted_at":    (agent_entry.get("timestamp") or "")[:19] if agent_entry else "",
            "recovered_at":      recovered_at.strftime("%H:%M:%S") if recovered_at else "TIMEOUT",
            "mttr_s":            mttr_s,
            "action":            agent_entry.get("action") if agent_entry else None,
            "confidence":        agent_entry.get("confidence") if agent_entry else None,
            "llm_latency_s":     agent_entry.get("llm_latency_s") if agent_entry else None,
            "baseline_cpu_pct":  baseline["cpu_pct"],
            "peak_cpu_pct":      round(self._prom_query("100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)"), 1),
            "baseline_mem_pct":  baseline["memory_pct"],
            "peak_mem_pct":      round(self._prom_query("(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100"), 1),
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
