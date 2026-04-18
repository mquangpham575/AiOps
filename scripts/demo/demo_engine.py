import csv
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
import yaml

from global_settings import (
    ROOT_DIR, RESULTS_DIR, TARGET_URL, AGENT_URL, PROMETHEUS_URL,
    AGENT_KEY, SSH_KEY_PATH, SCENARIO_TIMEOUT_S, POLL_INTERVAL_S,
    PROM_POLL_S, resolve_docker_host, CONFIG_PATH
)

def _fmt_stat(values: list[float | None]) -> str:
    valid = [v for v in values if v is not None]
    if not valid:
        return "N/A"
    mean = sum(valid) / len(valid)
    if len(valid) < 2:
        return f"{mean:.2f}"
    var = sum((v - mean) ** 2 for v in valid) / (len(valid) - 1)
    return f"{mean:.2f}±{math.sqrt(var):.2f}"

def _calc_increase_pct(baseline: float | None, current: float | None) -> float | None:
    if baseline is None or current is None or baseline == 0:
        return None
    return round((current - baseline) / baseline * 100, 1)

class BaseDemoRunner:
    """Core engine for executing AIOps benchmarking scenarios."""
    
    def __init__(
        self,
        iterations: int = 1,
        duration: int = 120,
        target_url: str = TARGET_URL,
        agent_url: str = AGENT_URL,
        prometheus_url: str = PROMETHEUS_URL,
        agent_key: str = AGENT_KEY,
        results_dir: Path = RESULTS_DIR,
        json_output: bool = True,
    ):
        self.iterations = iterations
        self.duration = duration
        self.target_url = target_url
        self.agent_url = agent_url
        self.prometheus_url = prometheus_url
        self.agent_key = agent_key
        self.results_dir = results_dir
        self.json_output = json_output
        self.results = []
        self.json_data = {"scenarios": {}}

    # ── Display Helpers ───────────────────────────────────────────────────────
    
    def _print_scenario_header(self, name: str):
        print(f"\n{'=' * 80}")
        print(f" {name.upper()}")
        print(f"{'=' * 80}")

    def _print_phase_header(self, phase_name: str, duration: int):
        print(f"\n[PHASE] {phase_name} ({duration}s)")
        print(f"%-20s | %-7s | %-16s | %-7s" % ("Timestamp", "Rel (s)", "Throughput(RPS)", "CPU (%)"))
        print("-" * 60)

    def _print_phase_footer(self):
        print("-" * 60)

    # ── Prometheus Telemetry ──────────────────────────────────────────────────
    
    def _prom_query(self, query: str, default: float = 0.0) -> float:
        try:
            r = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query},
                timeout=5,
            )
            data = r.json()
            if data["status"] == "success" and data["data"]["result"]:
                val = float(data["data"]["result"][0]["value"][1])
                if math.isnan(val) or math.isinf(val):
                    return default
                return val
        except Exception:
            pass
        return default

    # ── Orchestration Core ────────────────────────────────────────────────────
    
    def _start_injection(self, injection_cfg: dict, duration: int) -> subprocess.Popen | None:
        if not injection_cfg:
            return None
        method = injection_cfg.get("method")
        container = injection_cfg.get("container", "target-app")
        
        if method == "stress-ng":
            cmd_str = injection_cfg["command"].format(duration=duration)
            app_ip = os.environ.get("AZURE_APP_IP")
            
            if app_ip:
                # SSH Injection Pattern
                return subprocess.Popen(
                    ["ssh", "-o", "StrictHostKeyChecking=no", "-i", str(SSH_KEY_PATH), f"azureuser@{app_ip}", cmd_str],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            
            # Local Docker fallback
            return subprocess.Popen(
                ["docker", "exec", container] + cmd_str.split(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        return None

    def _wait_for_alert(self, alert_names: list[str], after: datetime, timeout: int = 60) -> datetime | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = requests.get(f"{self.prometheus_url}/api/v1/alerts", timeout=5)
                data = r.json()
                for alert in data.get("data", {}).get("alerts", []):
                    if alert.get("labels", {}).get("alertname") in alert_names and alert.get("state") == "firing":
                        active_at = datetime.fromisoformat(alert.get("activeAt", "").replace("Z", "+00:00"))
                        if active_at > after:
                            return active_at
            except Exception: pass
            time.sleep(PROM_POLL_S)
        return None

    def _find_agent_action(self, after: datetime, scenario: str) -> dict | None:
        try:
            r = requests.get(f"{self.agent_url}/logs", headers={"X-Agent-Key": self.agent_key}, timeout=5)
            logs = r.json()
            for entry in reversed(logs):
                ts = datetime.fromisoformat(entry.get("timestamp", "").replace("Z", "+00:00"))
                if ts > after and entry.get("scenario") == scenario and entry.get("action"):
                    return entry
        except Exception: pass
        return None

    def _stop_proc(self, proc: subprocess.Popen | None):
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except:
                try: proc.kill()
                except: pass

    # ── Execution Logic (Unified Heartbeat) ───────────────────────────────────

    def _start_locust_phase(self, tags: str, duration: int) -> subprocess.Popen:
        """Starts a Locust load generation process."""
        env = {**os.environ, "ATTACK_PROFILE": tags}
        log_path = self.results_dir / f"locust_{tags}.log"
        return subprocess.Popen(
            [
                sys.executable, "-m", "locust",
                "-f", str(ROOT_DIR / "tests" / "performance" / "locustfile.py"),
                f"--host={self.target_url}",
                "--run-time", f"{duration}s",
                "--headless", "--tags", tags,
                "--csv", str(self.results_dir / "temp_locust"),
            ],
            stdout=open(log_path, "w"),
            stderr=subprocess.STDOUT,
            env=env,
        )

    def run_throughput_phase(self, phase_name: str, tags: str, duration: int) -> dict:
        """Executes a single throughput phase with live telemetry."""
        self._print_phase_header(phase_name, duration)
        start_time = time.time()
        proc = self._start_locust_phase(tags, duration)
        
        last_pulse = 0
        try:
            while time.time() < (start_time + duration):
                now = time.time()
                if now - last_pulse >= 5:
                    cpu = self._prom_query("sum(rate(container_cpu_usage_seconds_total{name='target-app'}[1m])) * 100")
                    rps = self._prom_query("sum(rate(flask_http_request_total{job='target-app'}[1m]))")
                    ts = datetime.now().strftime("%H:%M:%S")
                    print("%-20s | %-7s | %-16.2f | %-7.2f" % (ts, f"{int(now - start_time)}s", rps, cpu))
                    last_pulse = now
                time.sleep(1)
            
            # Final snapshot
            final_cpu = self._prom_query("sum(rate(container_cpu_usage_seconds_total{name='target-app'}[1m])) * 100")
            final_rps = self._prom_query("sum(rate(flask_http_request_total{job='target-app'}[1m]))")
            return {"phase": phase_name, "cpu_pct": final_cpu, "throughput_rps": final_rps}
        finally:
            self._stop_proc(proc)
            self._print_phase_footer()

    def run_remediation_cycle(self, scenario_key: str, scenario_cfg: dict, iteration: int):
        """Standard remediation loop for CPU/Memory scenarios."""
        phase_dur = self.duration
        metrics_q = scenario_cfg.get("metrics", {})
        alerts = scenario_cfg.get("alerts", [])
        agent_scenario = scenario_cfg.get("agent_scenario") or scenario_key
        
        self._print_phase_header("LIFECYCLE", phase_dur)
        start_time = time.time()
        t0 = datetime.now(timezone.utc)
        
        # Injection
        proc = self._start_injection(scenario_cfg.get("injection"), phase_dur)
        
        t1, t2, t3 = None, None, None
        last_pulse = 0
        
        try:
            while time.time() < (start_time + phase_dur):
                now = time.time()
                if now - last_pulse >= 5:
                    # 1. Pulse Telemetry
                    cpu = self._prom_query("sum(rate(container_cpu_usage_seconds_total{name='target-app'}[1m])) * 100")
                    rps = self._prom_query("sum(rate(flask_http_request_total{job='target-app'}[1m]))")
                    ts = datetime.now().strftime("%H:%M:%S")
                    print("%-20s | %-7s | %-16.2f | %-7.2f" % (ts, f"{int(now - start_time)}s", rps, cpu))
                    last_pulse = now

                    # 2. Monitor Recovery
                    if alerts:
                        if not t1:
                            t1 = self._wait_for_alert(alerts, after=t0, timeout=1)
                            if t1:
                                t1_local = t1.astimezone()
                                print(f">> ALERT DETECTED: {t1_local.strftime('%H:%M:%S')}")
                        if t1 and not t2:
                            entry = self._find_agent_action(after=t0, scenario=agent_scenario)
                            if entry:
                                t2 = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                                t2_local = t2.astimezone()
                                print(f">> AGENT ACTED: {entry['action']} at {t2_local.strftime('%H:%M:%S')}")
                        if t2 and not t3:
                            if cpu < 30: # Hardcoded recovery for demo simple
                                t3 = datetime.now(timezone.utc)
                                print(f">> SYSTEM RECOVERED: MTTR={(t3-t0).total_seconds():.1f}s")
                                break
                time.sleep(1)
        finally:
            self._stop_proc(proc)
            self._print_phase_footer()
