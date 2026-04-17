"""
demo_runner.py — Config-driven AIOps Scenario Runner with JSON Export
=====================================================================

MỤC ĐÍCH:
  Chạy các kịch bản đánh giá hiệu năng AIOps với:
  - Multi-iteration runs với reproducibility
  - Prometheus metric collection
  - MTTR measurement (T0→T1→T2→T3) cho remediation scenarios
  - Baseline vs Load comparison (intra-run)
  - JSON export cho báo cáo

BASELINE COMPARISON:
  Mỗi throughput iteration chạy 2 phases:
    Phase 1: baseline (light load) → đo performance nền
    Phase 2: load (heavy load) → đo degradation
  Comparison được tính tự động: (load - baseline) / baseline * 100%

OUTPUT FILES:
  results/{scenario}/
  ├── runs/
  │   ├── run_001/
  │   │   ├── baseline_stats.csv    # Locust native CSV
  │   │   ├── load_stats.csv       # Locust native CSV
  │   │   └── metrics.json         # Prometheus metrics snapshot
  │   ├── run_002/
  │   └── run_003/
  ├── summary.json                  # Aggregated stats (mean ± stdev)
  ├── comparison.json               # Baseline vs Load comparison
  └── metadata.json                 # Run metadata

CÁCH DÙNG:
  # Chạy tất cả scenarios
  python scripts/demo_runner.py --scenario all --json-output

  # Chạy riêng từng scenario
  python scripts/demo_runner.py --scenario throughput --json-output
  python scripts/demo_runner.py --scenario cpu --json-output

  # Với custom parameters
  python scripts/demo_runner.py --scenario throughput --iterations 3 --duration 300 --json-output
"""

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from dotenv import load_dotenv

load_dotenv()

# ── Resolve paths ───────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "tests" / "performance" / "scenarios.yml"
RESULTS_DIR = ROOT_DIR / "results"

# ── Environment-based service URLs ───────────────────────────────────────────
_azure_ip = os.environ.get("AZURE_VM_IP") or os.environ.get("AZURE_APP_IP")
_default_target = f"http://{_azure_ip}:80" if _azure_ip else "http://localhost:5000"

TARGET_URL = os.environ.get("TARGET_URL", _default_target)
AGENT_URL = os.environ.get(
    "AGENT_URL", f"http://{_azure_ip}:8083" if _azure_ip else "http://localhost:8083"
)
PROMETHEUS_URL = os.environ.get(
    "PROMETHEUS_URL",
    f"http://{_azure_ip}:9090" if _azure_ip else "http://localhost:9090",
)
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


# ── Statistics helpers ────────────────────────────────────────────────────────


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _fmt_stat(values: list[float | None], precision: int = 1) -> str:
    """Format as mean±stdev string."""
    clean = [v for v in values if v is not None]
    if not clean:
        return "N/A"
    m = _mean(clean)
    s = _stdev(clean)
    return f"{m:.{precision}f}±{s:.{precision}f}"


def _calc_increase_pct(baseline: float, load: float) -> float | None:
    """Calculate percentage increase from baseline to load."""
    if baseline is None or load is None or baseline == 0:
        return None
    return round((load - baseline) / baseline * 100, 2)


# ── CSV field order ───────────────────────────────────────────────────────────
CSV_FIELDS = [
    "scenario",
    "iteration",
    "phase",
    "latency_p50_ms",
    "latency_p95_ms",
    "latency_p99_ms",
    "throughput_rps",
    "error_rate_pct",
    "cpu_pct",
    "memory_pct",
    "agent_cpu_pct",
    "agent_memory_mb",
    "detection_s",
    "response_s",
    "remediation_s",
    "mttr_s",
    "peak_cpu_pct",
    "peak_memory_pct",
    "restart_count",
    "action",
    "confidence",
]


class DemoRunner:
    def __init__(
        self,
        config: dict | None = None,
        target_url: str = TARGET_URL,
        agent_url: str = AGENT_URL,
        prometheus_url: str = PROMETHEUS_URL,
        agent_key: str = AGENT_KEY,
        results_dir: Path = RESULTS_DIR,
        iterations: int | None = None,
        duration: int | None = None,
        json_output: bool = False,
    ):
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
        self.iterations = iterations or self.defaults.get("iterations", 3)
        self.duration = duration or self.defaults.get("duration", 300)
        self.cooldown = self.defaults.get("cooldown", 90)
        self.cooldown_between = self.defaults.get("cooldown_between", 120)
        self.json_output = json_output
        self.results_dir = Path(results_dir)
        self.results: list[dict] = []
        self.json_data: dict[str, Any] = {"metadata": {}, "scenarios": {}}

    # ── Backwards-compatible test helpers ───────────────────────────────────

    def find_agent_action(self, after: datetime, scenario: str) -> dict | None:
        return self._find_agent_action(after=after, scenario=scenario)

    def wait_for_alert_fired(
        self, alert_names: list[str], after: datetime
    ) -> datetime | None:
        return self._wait_for_alert(alert_names=alert_names, after=after)

    def wait_for_recovery(
        self, query: str, threshold: float, consecutive_polls: int = 3
    ) -> datetime | None:
        return self._wait_for_recovery(
            query=query, threshold=threshold, consecutive_required=consecutive_polls
        )

    def record_baseline(self) -> dict:
        """Convenience baseline snapshot used by unit tests."""
        cpu_pct = self._prom_query(
            'rate(container_cpu_usage_seconds_total{name="target-app"}[1m]) * 100'
        )
        mem_pct = self._prom_query(
            'container_memory_usage_bytes{name="target-app"} / container_spec_memory_limit_bytes{name="target-app"} * 100'
        )
        lat_s = self._prom_query(
            'rate(flask_http_request_duration_seconds_sum{job="target-app"}[1m]) / rate(flask_http_request_duration_seconds_count{job="target-app"}[1m])'
        )
        return {
            "cpu_pct": round(cpu_pct, 2),
            "memory_pct": round(mem_pct, 2),
            "latency_ms": round(lat_s * 1000, 1),
        }

    # ── JSON helpers ─────────────────────────────────────────────────────────

    def _init_json_scenario(self, scenario_key: str, cfg: dict) -> dict:
        """Initialize JSON structure for a scenario."""
        return {
            "name": cfg.get("name", scenario_key),
            "description": cfg.get("description", ""),
            "goal": cfg.get("goal", ""),
            "evaluation_targets": cfg.get("evaluation_targets", []),
            "iterations": self.iterations,
            "duration_per_phase": self.duration,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "runs": [],
            "summary": {},
            "comparison": {},
        }

    def _save_run_json(
        self,
        scenario_key: str,
        iteration: int,
        phase: str,
        metrics: dict,
        extra_data: dict = None,
    ) -> Path:
        """Save metrics for a single run/phase to JSON file."""
        scenario_dir = self.results_dir / scenario_key / "runs" / f"run_{iteration:03d}"
        scenario_dir.mkdir(parents=True, exist_ok=True)

        run_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iteration": iteration,
            "phase": phase,
            "metrics": metrics,
        }
        if extra_data:
            run_data.update(extra_data)

        filepath = scenario_dir / f"{phase}_metrics.json"
        with open(filepath, "w") as f:
            json.dump(run_data, f, indent=2)
        return filepath

    def _export_json(self, scenario_key: str):
        """Export scenario summary and comparison to JSON files."""
        scenario_dir = self.results_dir / scenario_key
        scenario_dir.mkdir(parents=True, exist_ok=True)

        # Summary JSON
        summary_path = scenario_dir / "summary.json"
        with open(summary_path, "w") as f:
            json.dump(self.json_data["scenarios"].get(scenario_key, {}), f, indent=2)

        # Comparison JSON (if exists)
        if "comparison" in self.json_data["scenarios"].get(scenario_key, {}):
            comparison_path = scenario_dir / "comparison.json"
            with open(comparison_path, "w") as f:
                json.dump(
                    self.json_data["scenarios"][scenario_key]["comparison"], f, indent=2
                )

        return summary_path

    # ── Print helpers ─────────────────────────────────────────────────────────

    def _print_scenario_header(self, scenario_key: str, cfg: dict):
        name = cfg.get("name", scenario_key)
        desc = (cfg.get("description") or "").strip()
        goal = (cfg.get("goal") or "").strip()
        targets = cfg.get("evaluation_targets") or []

        print(f"\n{'=' * 70}")
        print(f"  {name}")
        print(f"{'=' * 70}")
        if desc:
            print(f"  {desc}")
        if goal:
            print(f"\n  Goal: {goal}")
        if targets:
            print("  Targets:")
            for t in targets:
                print(f"    - {t}")
        print(f"  Iterations: {self.iterations}")
        print(f"  Target:     {self.target_url}")
        print(f"  Prometheus: {self.prometheus_url}")
        print(f"  JSON Output: {'Enabled' if self.json_output else 'Disabled'}")
        print(f"{'=' * 70}")

    def _print_phase_header(self, phase_name: str, profile: str, duration: int):
        print(f"\n  ┌─ {phase_name.upper()} ─────────────────────────────────────")
        print(f"  │ Profile: {profile}")
        print(f"  │ Duration: {duration}s")
        print(f"  │ Tags: --tags {profile}")
        print(f"  │")

    def _print_phase_footer(self, metrics: dict):
        p50 = metrics.get("latency_p50_ms", "N/A")
        p95 = metrics.get("latency_p95_ms", "N/A")
        p99 = metrics.get("latency_p99_ms", "N/A")
        rps = metrics.get("throughput_rps", "N/A")
        err = metrics.get("error_rate_pct", "N/A")
        cpu = metrics.get("cpu_pct", "N/A")
        print(f"  │  p50={p50}ms | p95={p95}ms | p99={p99}ms")
        print(f"  │  rps={rps} | errors={err}% | cpu={cpu}%")
        print(f"  └──────────────────────────────────────────────────")

    # ── Prometheus helpers ────────────────────────────────────────────────────

    def _prom_query(self, query: str, default: float = 0.0) -> float:
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

    def _collect_metrics(self, metric_queries: dict) -> dict[str, float]:
        return {
            name: round(self._prom_query(q), 4) for name, q in metric_queries.items()
        }

    # ── Agent helpers ─────────────────────────────────────────────────────────

    def _agent_headers(self) -> dict:
        return {"X-Agent-Key": self.agent_key}

    def _find_agent_action(self, after: datetime, scenario: str) -> dict | None:
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
                    if (
                        ts > after
                        and entry.get("scenario") == scenario
                        and entry.get("action")
                    ):
                        return entry
                except ValueError:
                    continue
        except Exception:
            pass
        return None

    # ── Alert / recovery polling ──────────────────────────────────────────────

    def _wait_for_alert(
        self, alert_names: list[str], after: datetime
    ) -> datetime | None:
        deadline = time.time() + SCENARIO_TIMEOUT_S
        while time.time() < deadline:
            try:
                r = requests.get(f"{self.prometheus_url}/api/v1/alerts", timeout=5)
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

    def _wait_for_recovery(
        self, query: str, threshold: float, consecutive_required: int = 3
    ) -> datetime | None:
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

    # ── Preflight ─────────────────────────────────────────────────────────────

    def preflight(self) -> bool:
        checks = [
            (f"{self.target_url}/health", "target-app"),
            (f"{self.agent_url}/health", "agent"),
            (f"{self.prometheus_url}/-/ready", "prometheus"),
        ]
        all_ok = True
        print("\n  Pre-flight checks:")
        for url, name in checks:
            try:
                r = requests.get(url, timeout=5)
                icon = "✓" if r.status_code == 200 else "✗"
                print(f"    [{icon}] {name:15s} {url}")
                if r.status_code != 200:
                    all_ok = False
            except Exception as e:
                print(f"    [✗] {name:15s} UNREACHABLE: {e}")
                all_ok = False
        return all_ok

    # ── Fault injection ─────────────────────────────────────────────────────

    def _start_injection(
        self, scenario_cfg: dict, duration: int
    ) -> subprocess.Popen | None:
        injection = scenario_cfg.get("injection")
        if not injection:
            return None

        method = injection.get("method")

        if method == "stress-ng":
            cmd_str = injection["command"].format(duration=duration)
            container = injection.get("container", "target-app")
            
            # If we have an App IP, use it directly via SSH for reliability
            app_ip = os.environ.get("AZURE_APP_IP")
            if app_ip:
                print(f"    [INFO] Injecting stress via SSH to {app_ip}...")
                ssh_cmd = f"sudo docker exec {container} {cmd_str}"
                return subprocess.Popen(
                    ["ssh", "-o", "StrictHostKeyChecking=no", "-i", ".ssh/aiops3_key_rsa", f"azureuser@{app_ip}", ssh_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            
            # Local/Tunnel fallback
            env = {**os.environ}
            docker_host = _resolve_docker_host()
            if docker_host:
                env["DOCKER_HOST"] = docker_host
            return subprocess.Popen(
                ["docker", "exec", container] + cmd_str.split(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )

        if method == "locust":
            profile = injection.get("locust_profile", "memory")
            tags = injection.get("locust_tags", profile)
            env = {**os.environ, "ATTACK_PROFILE": profile}
            run_time = f"{duration}s"
            return subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "locust",
                    "-f",
                    str(ROOT_DIR / "tests" / "performance" / "locustfile.py"),
                    f"--host={self.target_url}",
                    "--run-time",
                    run_time,
                    "--headless",
                    "--tags",
                    tags,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )

        return None

    def _start_locust_phase(self, tags: str, duration: int) -> subprocess.Popen:
        env = {**os.environ, "ATTACK_PROFILE": tags}
        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "locust",
                "-f",
                str(ROOT_DIR / "tests" / "performance" / "locustfile.py"),
                f"--host={self.target_url}",
                "--run-time",
                f"{duration}s",
                "--headless",
                "--tags",
                tags,
                "--csv",
                str(self.results_dir / "temp_locust"),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )

    def _stop_proc(self, proc: subprocess.Popen | None):
        if proc is None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    # ── Throughput scenario (baseline vs load) ───────────────────────────────

    def _run_throughput_phase(
        self,
        scenario_key: str,
        scenario_cfg: dict,
        phase_name: str,
        phase_cfg: dict,
        iteration: int,
    ) -> dict:
        tags = phase_cfg.get("locust_tags", phase_name)
        dur = phase_cfg.get("duration", self.duration)
        metrics_q = scenario_cfg.get("metrics", {})

        self._print_phase_header(phase_name, tags, dur)

        # Start locust
        proc = self._start_locust_phase(tags, dur)

        # Let traffic stabilize, then sample near the end
        settle = max(dur - 30, dur * 0.7)
        time.sleep(settle)

        # Collect metrics
        m = self._collect_metrics(metrics_q)
        proc.wait(timeout=dur + 90)

        # Build metrics dict with proper units
        result = {
            "scenario": scenario_key,
            "iteration": iteration,
            "phase": phase_name,
            "latency_p50_ms": round(m.get("latency_p50", 0) * 1000, 2),
            "latency_p95_ms": round(m.get("latency_p95", 0) * 1000, 2),
            "latency_p99_ms": round(m.get("latency_p99", 0) * 1000, 2),
            "throughput_rps": round(m.get("throughput", 0), 2),
            "error_rate_pct": round(m.get("error_rate", 0), 2),
            "cpu_pct": round(m.get("cpu_pct", 0), 2),
            "memory_pct": round(m.get("memory_pct", 0), 2),
            "agent_cpu_pct": round(m.get("agent_cpu", 0), 2),
            "agent_memory_mb": round(m.get("agent_memory", 0) / (1024 * 1024), 2)
            if m.get("agent_memory")
            else 0,
        }

        # Save to JSON if enabled
        if self.json_output:
            self._save_run_json(scenario_key, iteration, phase_name, result)

        self._print_phase_footer(result)

        # Add to CSV results
        self.results.append(result)

        return result

    def _run_throughput(self, scenario_key: str, scenario_cfg: dict) -> list[dict]:
        phases = scenario_cfg.get("phases", {})
        baseline_cfg = phases.get("baseline", {})
        load_cfg = phases.get("load", phases.get("load", {}))

        # Initialize JSON structure
        if self.json_output:
            self.json_data["scenarios"][scenario_key] = self._init_json_scenario(
                scenario_key, scenario_cfg
            )

        all_rows = []

        for i in range(1, self.iterations + 1):
            print(
                f"\n  ╔══ ITERATION {i}/{self.iterations} ══════════════════════════════════╗"
            )

            # Phase 1: Baseline
            print(f"  ║ BASELINE PHASE")
            baseline_row = self._run_throughput_phase(
                scenario_key, scenario_cfg, "baseline", baseline_cfg, i
            )
            all_rows.append(baseline_row)

            print(f"  ║ Cooldown {self.cooldown}s...")
            time.sleep(self.cooldown)

            # Phase 2: Load
            print(f"  ║ LOAD PHASE")
            load_row = self._run_throughput_phase(
                scenario_key, scenario_cfg, "load", load_cfg, i
            )
            all_rows.append(load_row)

            # Calculate intra-run comparison
            if self.json_output:
                comparison = self._calc_comparison(baseline_row, load_row, scenario_cfg)
                run_data = {
                    "iteration": i,
                    "baseline": baseline_row,
                    "load": load_row,
                    "comparison": comparison,
                }
                self.json_data["scenarios"][scenario_key]["runs"].append(run_data)

            if i < self.iterations:
                print(
                    f"  ╚══ Cooldown {self.cooldown_between}s before next iteration ══════╝"
                )
                time.sleep(self.cooldown_between)
            else:
                print(
                    f"  ╚═══════════════════════════════════════════════════════════════════╝"
                )

        # Calculate summary and comparison
        summary = self._summarize_throughput(all_rows, scenario_key)
        if self.json_output:
            self.json_data["scenarios"][scenario_key]["summary"] = summary
            self.json_data["scenarios"][scenario_key]["comparison"] = (
                self._final_comparison(summary, scenario_cfg)
            )

        return all_rows

    def _calc_comparison(self, baseline: dict, load: dict, scenario_cfg: dict) -> dict:
        """Calculate comparison between baseline and load phases."""
        comp = {}

        # Latency increases
        for key in ["latency_p50_ms", "latency_p95_ms", "latency_p99_ms"]:
            comp[f"{key}_increase_pct"] = _calc_increase_pct(
                baseline.get(key), load.get(key)
            )

        # Throughput increase
        comp["throughput_increase_pct"] = _calc_increase_pct(
            baseline.get("throughput_rps"), load.get("throughput_rps")
        )

        # Error rate delta
        baseline_err = baseline.get("error_rate_pct", 0)
        load_err = load.get("error_rate_pct", 0)
        comp["error_rate_delta_pct"] = round(load_err - baseline_err, 2)

        # Check pass criteria
        criteria = scenario_cfg.get("baseline_comparison", {}).get("pass_criteria", {})
        comp["pass_criteria"] = {}

        if "latency_p95_increase_max" in criteria:
            max_increase = criteria["latency_p95_increase_max"]
            actual = comp.get("latency_p95_ms_increase_pct", 0)
            comp["pass_criteria"]["latency_p95_increase"] = {
                "expected_max": max_increase,
                "actual": actual,
                "passed": actual <= max_increase if actual is not None else True,
            }

        if "error_rate_under_load_max" in criteria:
            max_err = criteria["error_rate_under_load_max"]
            comp["pass_criteria"]["error_rate"] = {
                "expected_max": max_err,
                "actual": load_err,
                "passed": load_err <= max_err,
            }

        return comp

    def _final_comparison(self, summary: dict, scenario_cfg: dict) -> dict:
        """Calculate final comparison from summary stats."""
        baseline_summary = summary.get("baseline", {})
        load_summary = summary.get("load", {})

        final_comp = {
            "type": "intra_run",
            "description": "Baseline vs Load comparison within each iteration",
            "baseline_summary": baseline_summary,
            "load_summary": load_summary,
        }

        # Calculate increases from summary stats
        criteria = scenario_cfg.get("baseline_comparison", {}).get("pass_criteria", {})

        for key in ["latency_p50_ms", "latency_p95_ms", "latency_p99_ms"]:
            baseline_val = self._parse_stat_value(baseline_summary.get(key))
            load_val = self._parse_stat_value(load_summary.get(key))
            increase = _calc_increase_pct(baseline_val, load_val)
            if increase is not None:
                final_comp[f"{key}_increase_pct"] = increase

        # Overall pass/fail
        final_comp["overall_pass"] = True
        if "latency_p95_increase_max" in criteria:
            actual = final_comp.get("latency_p95_ms_increase_pct", 0)
            passed = actual <= criteria["latency_p95_increase_max"] if actual else True
            final_comp["overall_pass"] = final_comp["overall_pass"] and passed

        # Recommendation
        final_comp["recommendation"] = self._generate_recommendation(
            final_comp, criteria
        )

        return final_comp

    def _parse_stat_value(self, stat_str: str) -> float | None:
        """Parse mean±stdev string to get mean value."""
        if not stat_str or stat_str == "N/A":
            return None
        try:
            return float(stat_str.split("±")[0])
        except (ValueError, IndexError):
            return None

    def _generate_recommendation(self, comparison: dict, criteria: dict) -> str:
        """Generate recommendation based on comparison results."""
        p95_increase = comparison.get("latency_p95_ms_increase_pct")

        if p95_increase is None:
            return "Unable to generate recommendation - insufficient data"

        if p95_increase < 100:
            return f"System performs well under load. p95 latency increases {p95_increase}% (within acceptable range)."
        elif p95_increase < 300:
            return f"System shows moderate degradation under load. p95 latency increases {p95_increase}% (acceptable with monitoring)."
        else:
            return f"System requires capacity planning. p95 latency increases {p95_increase}% (exceeds threshold)."

    def _summarize_throughput(self, rows: list[dict], scenario_key: str) -> dict:
        """Summarize all iterations for each phase."""
        phases = list(set(r["phase"] for r in rows))
        summary = {}

        for phase in phases:
            phase_rows = [r for r in rows if r["phase"] == phase]

            phase_summary = {}
            for key in [
                "latency_p50_ms",
                "latency_p95_ms",
                "latency_p99_ms",
                "throughput_rps",
                "error_rate_pct",
                "cpu_pct",
                "memory_pct",
            ]:
                values = [r.get(key) for r in phase_rows]
                phase_summary[key] = _fmt_stat(values)

            summary[phase] = phase_summary

        return summary

    # ── Remediation scenarios (CPU/Memory MTTR) ──────────────────────────────

    def _run_remediation(self, scenario_key: str, scenario_cfg: dict) -> list[dict]:
        alerts = scenario_cfg.get("alerts", [])
        agent_scenario = scenario_cfg.get("agent_scenario") or scenario_key
        recovery_cfg = scenario_cfg.get("recovery", {})
        recovery_query = recovery_cfg.get("query", "").strip()
        recovery_threshold = recovery_cfg.get("threshold", 50)
        consecutive = recovery_cfg.get("consecutive_polls", 3)
        metrics_q = scenario_cfg.get("metrics", {})

        # Initialize JSON structure
        if self.json_output:
            self.json_data["scenarios"][scenario_key] = self._init_json_scenario(
                scenario_key, scenario_cfg
            )

        rows = []

        for i in range(1, self.iterations + 1):
            print(
                f"\n  ╔══ ITERATION {i}/{self.iterations} ══════════════════════════════════╗"
            )
            t0 = datetime.now(timezone.utc)

            # Baseline snapshot
            baseline = self._collect_metrics(metrics_q)
            print(
                f"  ║ Baseline: CPU={baseline.get('cpu_container', 0):.1f}% | "
                f"Memory={baseline.get('memory_container', 0):.1f}%"
            )

            # Inject fault
            proc = self._start_injection(scenario_cfg, self.duration)
            print(f"  ║ Fault injected (duration: {self.duration}s)")

            # T1: wait for alert
            print(f"  ║ Waiting for alert {alerts}...")
            t1 = self._wait_for_alert(alerts, after=t0)
            if t1:
                print(f"  ║ Alert fired   T1={t1.strftime('%H:%M:%S')}")
            else:
                print(f"  ║ Alert not detected within timeout")

            # T2: wait for agent action
            agent_entry = None
            deadline = time.time() + SCENARIO_TIMEOUT_S
            while time.time() < deadline:
                agent_entry = self._find_agent_action(after=t0, scenario=agent_scenario)
                if agent_entry:
                    print(
                        f"  ║ Agent acted   T2={agent_entry['timestamp'][11:19]}  "
                        f"action={agent_entry['action']}"
                    )
                    break
                time.sleep(POLL_INTERVAL_S)

            # T3: wait for recovery
            t3 = None
            if recovery_query:
                t3 = self._wait_for_recovery(
                    recovery_query, recovery_threshold, consecutive
                )

            self._stop_proc(proc)

            # Derive timestamps
            t2 = None
            if agent_entry and agent_entry.get("timestamp"):
                try:
                    t2 = datetime.fromisoformat(
                        agent_entry["timestamp"].replace("Z", "+00:00")
                    )
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
                print(
                    f"  ║ Recovered. MTTR={mttr_s}s  (detect={d} respond={rsp} remediate={rem})"
                )
            else:
                print(f"  ║ TIMEOUT — recovery not detected")

            print(
                f"  ╚═══════════════════════════════════════════════════════════════════╝"
            )

            row = {
                "scenario": scenario_key,
                "iteration": i,
                "phase": "remediation",
                "detection_s": detection_s,
                "response_s": response_s,
                "remediation_s": remediation_s,
                "mttr_s": mttr_s,
                "peak_cpu_pct": peak.get("cpu_container") or peak.get("cpu_host"),
                "peak_memory_pct": peak.get("memory_container")
                or peak.get("memory_host"),
                "restart_count": peak.get("restart_count"),
                "action": agent_entry.get("action") if agent_entry else None,
                "confidence": agent_entry.get("confidence") if agent_entry else None,
            }
            rows.append(row)
            self.results.append(row)

            # Save to JSON
            if self.json_output:
                self._save_run_json(scenario_key, i, "remediation", row)

            if i < self.iterations:
                print(f"\n  Cooldown {self.cooldown}s...")
                time.sleep(self.cooldown)

        # Summary
        summary = {
            "scenario": scenario_key,
            "iteration": "summary",
            "phase": "remediation",
            "detection_s": _fmt_stat([r["detection_s"] for r in rows]),
            "response_s": _fmt_stat([r["response_s"] for r in rows]),
            "remediation_s": _fmt_stat([r["remediation_s"] for r in rows]),
            "mttr_s": _fmt_stat([r["mttr_s"] for r in rows]),
            "peak_cpu_pct": _fmt_stat([r.get("peak_cpu_pct") for r in rows]),
            "peak_memory_pct": _fmt_stat([r.get("peak_memory_pct") for r in rows]),
        }
        rows.append(summary)

        # Update JSON
        if self.json_output:
            self.json_data["scenarios"][scenario_key]["summary"] = summary
            self.json_data["scenarios"][scenario_key]["comparison"] = {
                "type": "mttr_analysis",
                "mttr_summary": summary["mttr_s"],
                "detection_summary": summary["detection_s"],
                "response_summary": summary["response_s"],
                "remediation_summary": summary["remediation_s"],
            }

        return rows

    # ── Top-level run ────────────────────────────────────────────────────────

    def run(self, scenario: str = "all"):
        # Initialize metadata
        self.json_data["metadata"] = {
            "run_id": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config_path": str(CONFIG_PATH),
            "iterations": self.iterations,
            "duration_per_phase": self.duration,
            "target_url": self.target_url,
            "prometheus_url": self.prometheus_url,
            "agent_url": self.agent_url,
        }

        print("=" * 70)
        print("  AIOps Scenario Runner")
        print("=" * 70)
        print(f"  Config:     {CONFIG_PATH}")
        print(f"  Iterations: {self.iterations}")
        print(f"  Duration:   {self.duration}s")
        print(f"  JSON Output: {'Enabled' if self.json_output else 'Disabled'}")
        print(f"  Results Dir: {self.results_dir}")
        print()

        if not self.agent_key:
            print("  [WARN] AGENT_API_KEY not set")

        print("-- Pre-flight checks --")
        if not self.preflight():
            print("\nPre-flight failed — ensure docker-compose is up.")
            sys.exit(1)
        print("  All services healthy.\n")

        if scenario == "all":
            keys = list(self.scenarios.keys())
        else:
            if scenario not in self.scenarios:
                print(
                    f"Unknown scenario '{scenario}'. Available: {list(self.scenarios.keys())}"
                )
                sys.exit(1)
            keys = [scenario]

        for idx, key in enumerate(keys):
            cfg = self.scenarios[key]
            self._print_scenario_header(key, cfg)

            if key == "throughput":
                rows = self._run_throughput(key, cfg)
            else:
                rows = self._run_remediation(key, cfg)

            # Export JSON for this scenario
            if self.json_output:
                summary_path = self._export_json(key)
                print(f"\n  [JSON] Summary saved to: {summary_path}")

            if idx < len(keys) - 1:
                print(f"\n  Cooldown between scenarios: {self.cooldown_between}s...")
                time.sleep(self.cooldown_between)

        self._print_summary()
        self._export_csv()

        # Export final JSON
        if self.json_output:
            final_json_path = self.results_dir / "all_scenarios.json"
            with open(final_json_path, "w") as f:
                json.dump(self.json_data, f, indent=2)
            print(f"\n[JSON] All scenarios saved to: {final_json_path}")

    # ── Output ───────────────────────────────────────────────────────────────

    def _print_summary(self):
        if not self.results:
            return

        summaries = [r for r in self.results if r.get("iteration") == "summary"]
        print(f"\n{'=' * 70}")
        print("  SUMMARY (mean ± stdev)")
        print(f"{'=' * 70}")

        for s in summaries:
            sc = s["scenario"]
            ph = s["phase"]
            print(f"\n  [{sc} / {ph}]")
            for k, v in s.items():
                if k in ("scenario", "iteration", "phase") or not v:
                    continue
                print(f"    {k:25s} {v}")

        print(f"{'=' * 70}")

    def _export_csv(self):
        if not self.results:
            print("No results to export.")
            return

        # Create results directory
        self.results_dir.mkdir(parents=True, exist_ok=True)

        csv_path = self.results_dir / "results.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.results)
        print(f"\n[CSV] Results exported to {csv_path}")


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(
        description="AIOps Scenario Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/demo_runner.py --scenario all --json-output
  python scripts/demo_runner.py --scenario throughput --iterations 3 --json-output
  python scripts/demo_runner.py --scenario cpu --json-output --export results.csv
        """,
    )
    parser.add_argument(
        "--scenario", default="all", help="Scenario key from config, or 'all'"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Override number of iterations per scenario",
    )
    parser.add_argument(
        "--duration", type=int, default=None, help="Override phase duration in seconds"
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Enable JSON output for each run and summary",
    )
    parser.add_argument(
        "--export", default=None, help="CSV output path (default: results/results.csv)"
    )
    parser.add_argument(
        "--config", default=str(CONFIG_PATH), help="Path to scenarios config YAML"
    )
    parser.add_argument(
        "--target-url", default=None, help="Override target app base URL"
    )
    parser.add_argument("--agent-url", default=None, help="Override agent base URL")
    parser.add_argument(
        "--prometheus-url", default=None, help="Override Prometheus base URL"
    )
    parser.add_argument(
        "--agent-key", default=None, help="Override agent API key for /logs polling"
    )
    parser.add_argument(
        "--results-dir", default=None, help="Override results directory"
    )
    args = parser.parse_args()

    config = load_config(Path(args.config))

    runner = DemoRunner(
        config=config,
        iterations=args.iterations,
        duration=args.duration,
        json_output=args.json_output,
        target_url=args.target_url or TARGET_URL,
        agent_url=args.agent_url or AGENT_URL,
        prometheus_url=args.prometheus_url or PROMETHEUS_URL,
        agent_key=args.agent_key or AGENT_KEY,
        results_dir=Path(args.results_dir) if args.results_dir else RESULTS_DIR,
    )
    runner.run(scenario=args.scenario)


if __name__ == "__main__":
    main()
