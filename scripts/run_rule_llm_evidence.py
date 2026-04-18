import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEMO_RUNNER = ROOT_DIR / "scripts" / "demo_runner.py"
# Remote Configuration
SSH_IP = "104.215.158.157"
SSH_USER = "azureuser"
SSH_KEY = str(ROOT_DIR / ".ssh" / "aiops3_key_rsa")
REMOTE_DIR = "AiOps/ops/infra"
COMPOSE_FILE = "docker-compose.control.yml"  # Relative to REMOTE_DIR


def _run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and stream output to the console in real-time."""
    print(f"  [EXEC] {' '.join(cmd)}")
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env
    ) as proc:
        output = []
        for line in proc.stdout:
            print(f"    | {line.strip()}")
            output.append(line)
        proc.wait()
        if check and proc.returncode != 0:
            raise RuntimeError(f"Command failed with exit {proc.returncode}")
        return subprocess.CompletedProcess(cmd, proc.returncode, "".join(output), "")


def _compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run docker compose on the remote Control Node via SSH."""
    remote_cmd = f"cd {REMOTE_DIR} && sudo docker compose -f {COMPOSE_FILE} {' '.join(args)}"
    ssh_cmd = [
        "ssh", "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
        "-i", SSH_KEY,
        f"{SSH_USER}@{SSH_IP}",
        remote_cmd
    ]
    return _run_cmd(ssh_cmd, check=check)


def _start_tunnel() -> subprocess.Popen:
    """Start an SSH tunnel for agent telemetry."""
    print("  [TUNNEL] Establishing secure port forwarding...")
    tunnel_cmd = [
        "ssh", "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
        "-i", SSH_KEY,
        "-L", "8083:localhost:8083",
        "-L", "5001:localhost:5001",
        "-N",  # Do not execute remote command
        f"{SSH_USER}@{SSH_IP}"
    ]
    # No shell=True for security
    return subprocess.Popen(tunnel_cmd)


import time

def set_agent_mode(mode: str) -> None:
    if mode == "llm":
        _compose("up", "-d", "ai-agent")
        _compose("stop", "rule-based-agent")
        print("  [WAIT] Sleeping 10s for AI Agent startup...")
        time.sleep(10)
        return
    if mode == "rule":
        _compose("up", "-d", "rule-based-agent")
        _compose("stop", "ai-agent")
        print("  [WAIT] Sleeping 10s for Rule Agent startup...")
        time.sleep(10)
        return
    raise ValueError(f"Unsupported mode: {mode}")


def restore_agents() -> None:
    _compose("up", "-d", "ai-agent", "rule-based-agent")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_summary_metric(summary: dict, phase: str, key: str) -> float | None:
    phase_data = summary.get("summary", {}).get(phase, {})
    value = phase_data.get(key)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        head = value.split("±", 1)[0].strip()
        try:
            return float(head)
        except ValueError:
            return None
    return None


def _collect_mode_artifacts(mode_dir: Path, scenario: str) -> dict:
    scenario_dir = mode_dir / scenario
    summary_path = scenario_dir / "summary.json"
    comparison_path = scenario_dir / "comparison.json"
    baseline_ts = scenario_dir / "timeseries_baseline.csv"
    lifecycle_ts = scenario_dir / "timeseries_lifecycle.csv"

    summary = _read_json(summary_path)
    comparison = _read_json(comparison_path)

    return {
        "mode": mode_dir.name,
        "paths": {
            "summary": str(summary_path),
            "comparison": str(comparison_path),
            "timeseries_baseline": str(baseline_ts),
            "timeseries_lifecycle": str(lifecycle_ts),
        },
        "summary": summary,
        "comparison": comparison,
    }


def _build_side_by_side(rule_data: dict, llm_data: dict, scenario: str, run_id: str) -> dict:
    tracked = [
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_p99_ms",
        "throughput_rps",
        "error_rate_pct",
        "cpu_pct",
        "memory_pct",
    ]

    rule_summary = rule_data.get("summary", {})
    llm_summary = llm_data.get("summary", {})

    phase_pair = {
        "baseline": "baseline",
        "comparison": "lifecycle",
    }

    deltas = {}
    excluded_metrics = []
    for metric in tracked:
        r_val = _extract_summary_metric(rule_summary, "lifecycle", metric)
        l_val = _extract_summary_metric(llm_summary, "lifecycle", metric)

        if r_val is None or l_val is None:
            excluded_metrics.append(metric)
            continue

        deltas[metric] = {
            "rule": r_val,
            "llm": l_val,
            "absolute_delta": round(l_val - r_val, 6),
            "delta_pct_vs_rule": round(((l_val - r_val) / r_val) * 100, 4) if r_val != 0 else None,
        }

    return {
        "run_id": run_id,
        "scenario": scenario,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase_pair": phase_pair,
        "metric_basis": "normalized_canonical",
        "rule": {
            "paths": rule_data.get("paths", {}),
            "comparison": rule_data.get("comparison", {}),
        },
        "llm": {
            "paths": llm_data.get("paths", {}),
            "comparison": llm_data.get("comparison", {}),
        },
        "deltas": deltas,
        "excluded_metrics": sorted(excluded_metrics),
    }


def run_mode(
    mode: str,
    scenario: str,
    iterations: int,
    duration: int,
    mode_results_dir: Path,
    target_url: str | None,
    prometheus_url: str | None,
    llm_agent_url: str,
    rule_agent_url: str,
) -> None:
    set_agent_mode(mode)
    agent_url = llm_agent_url if mode == "llm" else rule_agent_url

    cmd = [
        sys.executable,
        str(DEMO_RUNNER),
        "--scenario",
        scenario,
        "--iterations",
        str(iterations),
        "--duration",
        str(duration),
        "--results-dir",
        str(mode_results_dir),
        "--agent-url",
        agent_url,
    ]

    if target_url:
        cmd.extend(["--target-url", target_url])
    if prometheus_url:
        cmd.extend(["--prometheus-url", prometheus_url])

    result = _run_cmd(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"demo_runner failed in {mode} mode (exit={result.returncode})\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run isolated Rule-vs-LLM evidence workflow")
    parser.add_argument("--scenario", required=True, help="Scenario key (e.g., demo_cpu)")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--results-root", default=str(ROOT_DIR / "results" / "evidence"))
    parser.add_argument("--target-url", default=None)
    parser.add_argument("--prometheus-url", default=None)
    parser.add_argument("--llm-agent-url", default="http://localhost:8083")
    parser.add_argument("--rule-agent-url", default="http://localhost:5001")
    parser.add_argument("--run-id", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    root = Path(args.results_root)
    run_root = root / run_id
    llm_dir = run_root / "llm"
    rule_dir = run_root / "rule"
    comp_dir = run_root / "comparison"

    llm_dir.mkdir(parents=True, exist_ok=True)
    rule_dir.mkdir(parents=True, exist_ok=True)
    comp_dir.mkdir(parents=True, exist_ok=True)

    tunnel_proc = _start_tunnel()
    try:
        run_mode(
            mode="llm",
            scenario=args.scenario,
            iterations=args.iterations,
            duration=args.duration,
            mode_results_dir=llm_dir,
            target_url=args.target_url,
            prometheus_url=args.prometheus_url,
            llm_agent_url=args.llm_agent_url,
            rule_agent_url=args.rule_agent_url,
        )

        print("\n[COOLDOWN] Stabilizing environment for 15s before next phase...")
        restore_agents()
        time.sleep(15)

        run_mode(
            mode="rule",
            scenario=args.scenario,
            iterations=args.iterations,
            duration=args.duration,
            mode_results_dir=rule_dir,
            target_url=args.target_url,
            prometheus_url=args.prometheus_url,
            llm_agent_url=args.llm_agent_url,
            rule_agent_url=args.rule_agent_url,
        )
    finally:
        print("\n[CLEANUP] Restoring agents and closing tunnel...")
        restore_agents()
        tunnel_proc.terminate()

    llm_data = _collect_mode_artifacts(llm_dir, args.scenario)
    rule_data = _collect_mode_artifacts(rule_dir, args.scenario)

    consolidated = _build_side_by_side(rule_data, llm_data, args.scenario, run_id)
    out_path = comp_dir / f"rule_vs_llm_{args.scenario}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(consolidated, f, indent=2)

    print(f"[OK] Evidence generated: {out_path}")


if __name__ == "__main__":
    main()
