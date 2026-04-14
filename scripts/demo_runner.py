"""
demo_runner.py — Config-driven AIOps scenario runner with multi-iteration
statistical analysis.

Reads scenario definitions from scenarios/config.yml and orchestrates:
  - Multi-iteration runs with cooldown periods
  - Prometheus metric collection (latency percentiles, throughput, CPU, memory)
  - MTTR measurement (T0→T1→T2→T3) for remediation scenarios
  - CSV export with per-iteration rows + summary rows (mean ± stdev)

Usage:
    python scripts/demo_runner.py --scenario all
    python scripts/demo_runner.py --scenario throughput --iterations 3 --duration 300
    python scripts/demo_runner.py --scenario cpu --export results.csv
"""

import argparse
import csv
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

load_dotenv()

# ── Resolve paths ────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "tests" / "performance" / "scenarios.yml"

# ── Environment-based service URLs ───────────────────────────
_azure_ip = os.environ.get("AZURE_VM_IP") or os.environ.get("AZURE_APP_IP")
_default_target = f"http://{_azure_ip}:80" if _azure_ip else "http://localhost:5000"

TARGET_URL = os.environ.get("TARGET_URL", _default_target)
AGENT_URL = os.environ.get("AGENT_URL", "http://localhost:8080")
PROMETHEUS_URL = "http://localhost:9090"
AGENT_KEY = os.environ.get("AGENT_API_KEY", "")

SCENARIO_TIMEOUT_S = 180
POLL_INTERVAL_S = 2
PROM_POLL_S = 3


def _resolve_docker_host() -> str | None:
    explicit = os.environ.get("DOCKER_HOST")
    if explicit:
        return explicit
    if _azure_ip:
        return "tcp://localhost:2375"
    return None


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _fmt_stat(values: list[float | None], precision: int = 1) -> str:
    clean = [v for v in values if v is not None]
    if not clean:
        return ""
    m = _mean(clean)
    s = _stdev(clean)
    return f"{m:.{precision}f}\u00b1{s:.{precision}f}"


# ── CSV field order ──────────────────────────────────────────
CSV_FIELDS = [
    "scenario", "iteration", "phase",
    "latency_p50_ms", "latency_p95_ms", "latency_p99_ms",
    "throughput_rps", "error_rate_pct",
    "cpu_pct", "memory_pct",
    "agent_cpu_pct", "agent_memory_mb",
    "detection_s", "response_s", "remediation_s", "mttr_s",
    "peak_cpu_pct", "peak_memory_pct", "restart_count",
    "action", "confidence",
]


class DemoRunner:
    def __init__(self, config: dict | None = None, target_url: str = TARGET_URL,
                 agent_url: str = AGENT_URL, prometheus_url: str = PROMETHEUS_URL,
                 agent_key: str = AGENT_KEY, export_file: str = "results.csv",
                 iterations: int | None = None, duration: int | None = None):
        if config is None:
            with open(CONFIG_PATH) as f:
                config = yaml.safe_load(f)
        self.config = config
        self.defaults = self.config.get("defaults", {})
        self.scenarios = self.config.get("scenarios", {})
        self.target_url = target_url
        self.agent_url = agent_url
        self.prometheus_url = prometheus_url
        self.agent_key = agent_key
        self.export_file = export_file
        # CLI overrides take precedence over config defaults
        self.iterations = iterations or self.defaults.get("iterations", 3)
        self.duration = duration or self.defaults.get("duration", 300)
        self.cooldown = self.defaults.get("cooldown", 90)
        self.cooldown_between = self.defaults.get("cooldown_between", 120)
        self.results: list[dict] = []

    # ── Backwards-compatible test helpers (public wrappers) ──

    def find_agent_action(self, after: datetime, scenario: str) -> dict | None:
        return self._find_agent_action(after=after, scenario=scenario)

    def wait_for_alert_fired(self, alert_names: list[str], after: datetime) -> datetime | None:
        return self._wait_for_alert(alert_names=alert_names, after=after)

    def wait_for_recovery(self, query: str, threshold: float, consecutive_polls: int = 3) -> datetime | None:
        return self._wait_for_recovery(query=query, threshold=threshold,
                                       consecutive_required=consecutive_polls)

    def export_csv(self):
        return self._export_csv()

    def record_baseline(self) -> dict:
        """Convenience baseline snapshot used by unit tests."""
        cpu_pct = self._prom_query('rate(container_cpu_usage_seconds_total{name="target-app"}[1m]) * 100')
        mem_pct = self._prom_query('container_memory_usage_bytes{name="target-app"} / container_spec_memory_limit_bytes{name="target-app"} * 100')
        lat_s = self._prom_query('rate(flask_http_request_duration_seconds_sum{job="target-app"}[1m]) / rate(flask_http_request_duration_seconds_count{job="target-app"}[1m])')
        return {
            "cpu_pct": round(cpu_pct, 2),
            "memory_pct": round(mem_pct, 2),
            "latency_ms": round(lat_s * 1000, 1),
        }

    def _print_scenario_header(self, scenario_key: str, cfg: dict):
        name = cfg.get("name", scenario_key)
        desc = (cfg.get("description") or "").strip()
        goal = (cfg.get("goal") or "").strip()
        targets = cfg.get("evaluation_targets") or []
        print(f"\n{'='*60}")
        print(f"  {name}")
        if desc:
            print(f"  {desc}")
        if goal:
            print(f"\n  Goal: {goal}")
        if targets:
            print("  Targets:")
            for t in targets:
                print(f"    - {t}")
        if scenario_key != "throughput":
            agent_scenario = cfg.get("agent_scenario") or scenario_key
            print(f"\n  Agent log scenario label: {agent_scenario}")
        print(f"  Target:     {self.target_url}")
        print(f"  Prometheus: {self.prometheus_url}")
        print(f"  Agent:      {self.agent_url}")
        print(f"{'='*60}")

    # ── Prometheus helpers ────────────────────────────────────

    def _prom_query(self, query: str, default: float = 0.0) -> float:
        try:
            r = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query}, timeout=5,
            )
            data = r.json()
            if data["status"] == "success" and data["data"]["result"]:
                return float(data["data"]["result"][0]["value"][1])
        except Exception:
            pass
        return default

    def _collect_metrics(self, metric_queries: dict) -> dict[str, float]:
        return {name: round(self._prom_query(q), 2) for name, q in metric_queries.items()}

    # ── Agent helpers ─────────────────────────────────────────

    def _agent_headers(self) -> dict:
        return {"X-Agent-Key": self.agent_key}

    def _find_agent_action(self, after: datetime, scenario: str) -> dict | None:
        try:
            r = requests.get(
                f"{self.agent_url}/logs",
                headers=self._agent_headers(), timeout=5,
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

    # ── Alert / recovery polling ──────────────────────────────

    def _wait_for_alert(self, alert_names: list[str], after: datetime) -> datetime | None:
        deadline = time.time() + SCENARIO_TIMEOUT_S
        while time.time() < deadline:
            try:
                r = requests.get(f"{self.prometheus_url}/api/v1/alerts", timeout=5)
                data = r.json()
                for alert in data.get("data", {}).get("alerts", []):
                    if (alert.get("labels", {}).get("alertname") in alert_names
                            and alert.get("state") == "firing"):
                        active_at_str = alert.get("activeAt", "")
                        try:
                            active_at = datetime.fromisoformat(active_at_str.replace("Z", "+00:00"))
                            if active_at > after:
                                return active_at
                        except ValueError:
                            pass
            except Exception:
                pass
            time.sleep(PROM_POLL_S)
        return None

    def _wait_for_recovery(self, query: str, threshold: float,
                           consecutive_required: int = 3) -> datetime | None:
        deadline = time.time() + SCENARIO_TIMEOUT_S
        consecutive = 0
        while time.time() < deadline:
            value = self._prom_query(query)
            if value < threshold:
                consecutive += 1
                if consecutive >= consecutive_required:
                    return datetime.now(timezone.utc)
            else:
                consecutive = 0
            time.sleep(PROM_POLL_S)
        return None

    # ── Preflight ─────────────────────────────────────────────

    def preflight(self) -> bool:
        checks = [
            (f"{self.target_url}/health", "target-app"),
            (f"{self.agent_url}/health", "agent"),
            (f"{self.prometheus_url}/-/ready", "prometheus"),
        ]
        all_ok = True
        for url, name in checks:
            try:
                r = requests.get(url, timeout=5)
                icon = "+" if r.status_code == 200 else "FAIL"
                print(f"  [{icon}] {name:15s} {url}")
                if r.status_code != 200:
                    all_ok = False
            except Exception as e:
                print(f"  [FAIL] {name:15s} UNREACHABLE: {e}")
                all_ok = False
        return all_ok

    # ── Fault injection ───────────────────────────────────────

    def _start_injection(self, scenario_cfg: dict, duration: int) -> subprocess.Popen | None:
        injection = scenario_cfg.get("injection")
        if not injection:
            return None

        method = injection.get("method")

        if method == "stress-ng":
            cmd = injection["command"].format(duration=duration)
            container = injection.get("container", "target-app")
            env = {**os.environ}
            docker_host = _resolve_docker_host()
            if docker_host:
                env["DOCKER_HOST"] = docker_host
            return subprocess.Popen(
                ["docker", "exec", container] + cmd.split(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
            )

        if method == "locust":
            profile = injection.get("locust_profile", "memory")
            tags = injection.get("locust_tags", profile)
            env = {**os.environ, "ATTACK_PROFILE": profile}
            run_time = f"{duration}s"
            return subprocess.Popen(
                [sys.executable, "-m", "locust",
                 "-f", str(ROOT_DIR / "tests" / "performance" / "locustfile.py"),
                 f"--host={self.target_url}",
                 "--run-time", run_time, "--headless", "--tags", tags],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
            )

        return None

    def _start_locust_phase(self, profile: str, duration: int) -> subprocess.Popen:
        env = {**os.environ, "ATTACK_PROFILE": profile}
        tags = "baseline" if profile == "baseline" else profile
        return subprocess.Popen(
            [sys.executable, "-m", "locust",
             "-f", str(ROOT_DIR / "tests" / "performance" / "locustfile.py"),
             f"--host={self.target_url}",
             "--run-time", f"{duration}s", "--headless", "--tags", tags],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
        )

    def _stop_proc(self, proc: subprocess.Popen | None):
        if proc is None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    # ── Scenario: throughput (multi-phase, no MTTR) ───────────

    def _run_throughput_phase(self, scenario_cfg: dict, phase_name: str,
                              phase_cfg: dict, iteration: int) -> dict:
        profile = phase_cfg.get("locust_profile", phase_name)
        dur = phase_cfg.get("duration", self.duration)
        metrics_q = scenario_cfg.get("metrics", {})

        print(f"    Phase [{phase_name}]: {dur}s with profile '{profile}'")
        proc = self._start_locust_phase(profile, dur)

        # Let traffic stabilize, then sample near the end
        settle = max(dur - 30, dur * 0.7)
        time.sleep(settle)

        m = self._collect_metrics(metrics_q)
        proc.wait(timeout=dur + 30)

        return {
            "scenario": "throughput", "iteration": iteration, "phase": phase_name,
            "latency_p50_ms": round(m.get("latency_p50", 0) * 1000, 1),
            "latency_p95_ms": round(m.get("latency_p95", 0) * 1000, 1),
            "latency_p99_ms": round(m.get("latency_p99", 0) * 1000, 1),
            "throughput_rps": round(m.get("throughput", 0), 1),
            "error_rate_pct": round(m.get("error_rate", 0), 2),
            "cpu_pct": round(m.get("cpu_pct", 0), 1),
            "memory_pct": round(m.get("memory_pct", 0), 1),
            "agent_cpu_pct": round(m.get("agent_cpu", 0), 1),
            "agent_memory_mb": round(m.get("agent_memory", 0) / (1024 * 1024), 1) if m.get("agent_memory") else 0,
        }

    def _run_throughput(self, scenario_cfg: dict) -> list[dict]:
        phases = scenario_cfg.get("phases", {})
        rows = []
        for i in range(1, self.iterations + 1):
            print(f"\n  Iteration {i}/{self.iterations}")
            for phase_name, phase_cfg in phases.items():
                row = self._run_throughput_phase(scenario_cfg, phase_name, phase_cfg, i)
                rows.append(row)
                self._print_throughput_row(row)
            if i < self.iterations:
                print(f"    Cooldown {self.cooldown}s...")
                time.sleep(self.cooldown)

        # Summary rows per phase
        for phase_name in phases:
            phase_rows = [r for r in rows if r["phase"] == phase_name]
            summary = self._summarize_throughput(phase_rows, phase_name)
            rows.append(summary)

        return rows

    def _print_throughput_row(self, r: dict):
        print(f"      p50={r['latency_p50_ms']}ms  p95={r['latency_p95_ms']}ms  "
              f"p99={r['latency_p99_ms']}ms  rps={r['throughput_rps']}  "
              f"err={r['error_rate_pct']}%  cpu={r['cpu_pct']}%  mem={r['memory_pct']}%")

    def _summarize_throughput(self, rows: list[dict], phase_name: str) -> dict:
        def agg(key):
            return _fmt_stat([r.get(key) for r in rows])

        return {
            "scenario": "throughput", "iteration": "summary", "phase": phase_name,
            "latency_p50_ms": agg("latency_p50_ms"),
            "latency_p95_ms": agg("latency_p95_ms"),
            "latency_p99_ms": agg("latency_p99_ms"),
            "throughput_rps": agg("throughput_rps"),
            "error_rate_pct": agg("error_rate_pct"),
            "cpu_pct": agg("cpu_pct"),
            "memory_pct": agg("memory_pct"),
            "agent_cpu_pct": agg("agent_cpu_pct"),
            "agent_memory_mb": agg("agent_memory_mb"),
        }

    # ── Scenario: remediation (cpu / memory — MTTR flow) ──────

    def _run_remediation(self, scenario_key: str, scenario_cfg: dict) -> list[dict]:
        alerts = scenario_cfg.get("alerts", [])
        agent_scenario = scenario_cfg.get("agent_scenario") or scenario_key
        recovery_cfg = scenario_cfg.get("recovery", {})
        recovery_query = recovery_cfg.get("query", "").strip()
        recovery_threshold = recovery_cfg.get("threshold", 50)
        consecutive = recovery_cfg.get("consecutive_polls", 3)
        metrics_q = scenario_cfg.get("metrics", {})
        rows = []

        for i in range(1, self.iterations + 1):
            print(f"\n  Iteration {i}/{self.iterations}")
            t0 = datetime.now(timezone.utc)

            # Baseline snapshot
            baseline = self._collect_metrics(metrics_q)
            print(f"    Baseline: {baseline}")

            # Inject fault
            proc = self._start_injection(scenario_cfg, self.duration)
            if proc:
                print(f"    Fault injected")
            else:
                print(f"    [WARN] No injection configured")

            # T1: wait for alert
            print(f"    Waiting for alert {alerts}...")
            t1 = self._wait_for_alert(alerts, after=t0)
            if t1:
                print(f"    Alert fired   T1={t1.strftime('%H:%M:%S')}")
            else:
                print(f"    Alert not detected within timeout")

            # T2: wait for agent action
            agent_entry = None
            deadline = time.time() + SCENARIO_TIMEOUT_S
            while time.time() < deadline:
                agent_entry = self._find_agent_action(after=t0, scenario=agent_scenario)
                if agent_entry:
                    print(f"    Agent acted   T2={agent_entry['timestamp'][11:19]}  "
                          f"action={agent_entry['action']}")
                    break
                time.sleep(POLL_INTERVAL_S)

            # T3: wait for recovery
            t3 = None
            if recovery_query:
                t3 = self._wait_for_recovery(recovery_query, recovery_threshold, consecutive)

            self._stop_proc(proc)

            # Derive timestamps
            t2 = None
            if agent_entry and agent_entry.get("timestamp"):
                try:
                    t2 = datetime.fromisoformat(agent_entry["timestamp"].replace("Z", "+00:00"))
                except ValueError:
                    pass

            detection_s = round((t1 - t0).total_seconds(), 1) if t1 else None
            response_s = round((t2 - t1).total_seconds(), 1) if (t2 and t1) else None
            remediation_s = round((t3 - t2).total_seconds(), 1) if (t3 and t2) else None
            mttr_s = round((t3 - t0).total_seconds(), 1) if t3 else None

            # Peak metrics
            peak = self._collect_metrics(metrics_q)

            if mttr_s:
                d = f"{detection_s}s" if detection_s is not None else "-"
                rsp = f"{response_s}s" if response_s is not None else "-"
                rem = f"{remediation_s}s" if remediation_s is not None else "-"
                print(f"    Recovered. MTTR={mttr_s}s  (detect={d} respond={rsp} remediate={rem})")
            else:
                print(f"    TIMEOUT — recovery not detected")

            row = {
                "scenario": scenario_key, "iteration": i, "phase": "remediation",
                "detection_s": detection_s,
                "response_s": response_s,
                "remediation_s": remediation_s,
                "mttr_s": mttr_s,
                "peak_cpu_pct": peak.get("cpu_container") or peak.get("cpu_host"),
                "peak_memory_pct": peak.get("memory_container") or peak.get("memory_host"),
                "restart_count": peak.get("restart_count"),
                "action": agent_entry.get("action") if agent_entry else None,
                "confidence": agent_entry.get("confidence") if agent_entry else None,
            }
            rows.append(row)

            if i < self.iterations:
                print(f"    Cooldown {self.cooldown}s...")
                time.sleep(self.cooldown)

        # Summary row
        summary = {
            "scenario": scenario_key, "iteration": "summary", "phase": "remediation",
            "detection_s": _fmt_stat([r["detection_s"] for r in rows]),
            "response_s": _fmt_stat([r["response_s"] for r in rows]),
            "remediation_s": _fmt_stat([r["remediation_s"] for r in rows]),
            "mttr_s": _fmt_stat([r["mttr_s"] for r in rows]),
            "peak_cpu_pct": _fmt_stat([r.get("peak_cpu_pct") for r in rows]),
            "peak_memory_pct": _fmt_stat([r.get("peak_memory_pct") for r in rows]),
        }
        rows.append(summary)
        return rows

    # ── Top-level run ─────────────────────────────────────────

    def run(self, scenario: str = "all"):
        print("=" * 60)
        print("  AIOps Scenario Runner")
        print("=" * 60)
        print(f"  Config:     {CONFIG_PATH}")
        print(f"  Iterations: {self.iterations}")
        print(f"  Duration:   {self.duration}s")
        print()

        if not self.agent_key:
            print("  [WARN] AGENT_API_KEY not set (agent /logs will likely be unauthorized)")

        print("-- Pre-flight checks --")
        if not self.preflight():
            print("\nPre-flight failed — ensure docker-compose is up.")
            sys.exit(1)
        print("  All services healthy.\n")

        if scenario == "all":
            keys = list(self.scenarios.keys())
        else:
            if scenario not in self.scenarios:
                print(f"Unknown scenario '{scenario}'. Available: {list(self.scenarios.keys())}")
                sys.exit(1)
            keys = [scenario]

        for idx, key in enumerate(keys):
            cfg = self.scenarios[key]
            self._print_scenario_header(key, cfg)

            if key == "throughput":
                rows = self._run_throughput(cfg)
            else:
                rows = self._run_remediation(key, cfg)

            self.results.extend(rows)

            if idx < len(keys) - 1:
                print(f"\n  Cooldown between scenarios: {self.cooldown_between}s...")
                time.sleep(self.cooldown_between)

        self._print_summary()
        self._export_csv()

    # ── Output ────────────────────────────────────────────────

    def _print_summary(self):
        if not self.results:
            return

        summaries = [r for r in self.results if r.get("iteration") == "summary"]
        print(f"\n{'='*70}")
        print("  SUMMARY (mean +/- stdev)")
        print(f"{'='*70}")

        for s in summaries:
            sc = s["scenario"]
            ph = s["phase"]
            print(f"\n  [{sc} / {ph}]")
            for k, v in s.items():
                if k in ("scenario", "iteration", "phase") or not v:
                    continue
                print(f"    {k:20s} {v}")

        print(f"{'='*70}")

    def _export_csv(self):
        if not self.results:
            print("No results to export.")
            return
        with open(self.export_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.results)
        print(f"\nResults exported to {self.export_file}")


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="AIOps Scenario Runner")
    parser.add_argument("--scenario", default="all",
                        help="Scenario key from config.yml, or 'all'")
    parser.add_argument("--iterations", type=int, default=None,
                        help="Override number of iterations per scenario")
    parser.add_argument("--duration", type=int, default=None,
                        help="Override phase duration in seconds")
    parser.add_argument("--export", default="results.csv",
                        help="CSV output path")
    parser.add_argument("--config", default=str(CONFIG_PATH),
                        help="Path to scenarios config YAML")
    parser.add_argument("--target-url", default=None,
                        help="Override target app base URL")
    parser.add_argument("--agent-url", default=None,
                        help="Override agent base URL (useful for AI vs rule-based compare)")
    parser.add_argument("--prometheus-url", default=None,
                        help="Override Prometheus base URL")
    parser.add_argument("--agent-key", default=None,
                        help="Override agent API key for /logs polling")
    args = parser.parse_args()

    config = load_config(Path(args.config))

    runner = DemoRunner(
        config=config,
        export_file=args.export,
        iterations=args.iterations,
        duration=args.duration,
        target_url=args.target_url or TARGET_URL,
        agent_url=args.agent_url or AGENT_URL,
        prometheus_url=args.prometheus_url or PROMETHEUS_URL,
        agent_key=args.agent_key or AGENT_KEY,
    )
    runner.run(scenario=args.scenario)


if __name__ == "__main__":
    main()
