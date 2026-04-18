import json
from pathlib import Path
from unittest.mock import patch

import pytest

import run_rule_llm_evidence as evidence


def test_set_agent_mode_llm_invokes_expected_compose_calls():
    calls = []

    def fake_compose(*args, **kwargs):
        calls.append(args)
        return None

    with patch("run_rule_llm_evidence._compose", side_effect=fake_compose):
        evidence.set_agent_mode("llm")

    assert calls == [
        ("up", "-d", "ai-agent"),
        ("stop", "rule-based-agent"),
    ]


def test_set_agent_mode_rule_invokes_expected_compose_calls():
    calls = []

    def fake_compose(*args, **kwargs):
        calls.append(args)
        return None

    with patch("run_rule_llm_evidence._compose", side_effect=fake_compose):
        evidence.set_agent_mode("rule")

    assert calls == [
        ("up", "-d", "rule-based-agent"),
        ("stop", "ai-agent"),
    ]


def test_set_agent_mode_rejects_unknown_mode():
    with pytest.raises(ValueError):
        evidence.set_agent_mode("invalid")


def test_extract_summary_metric_parses_mean_plus_stdev_string():
    summary = {
        "summary": {
            "lifecycle": {
                "throughput_rps": "12.34±0.12"
            }
        }
    }

    value = evidence._extract_summary_metric(summary, "lifecycle", "throughput_rps")
    assert value == pytest.approx(12.34)


def test_collect_mode_artifacts_loads_summary_and_comparison(tmp_path: Path):
    mode_dir = tmp_path / "llm"
    scenario_dir = mode_dir / "demo_cpu"
    scenario_dir.mkdir(parents=True)

    summary_payload = {"summary": {"baseline": {"throughput_rps": "1.0±0.0"}}}
    comparison_payload = {"overall_pass": True}

    (scenario_dir / "summary.json").write_text(json.dumps(summary_payload), encoding="utf-8")
    (scenario_dir / "comparison.json").write_text(json.dumps(comparison_payload), encoding="utf-8")

    out = evidence._collect_mode_artifacts(mode_dir, "demo_cpu")

    assert out["mode"] == "llm"
    assert out["summary"] == summary_payload
    assert out["comparison"] == comparison_payload
    assert out["paths"]["summary"].endswith("summary.json")


def test_build_side_by_side_generates_deltas_and_exclusions():
    rule_data = {
        "paths": {"summary": "rule/summary.json", "comparison": "rule/comparison.json"},
        "summary": {
            "summary": {
                "lifecycle": {
                    "throughput_rps": "2.0±0.0",
                    "latency_p95_ms": "150.0±0.0",
                }
            }
        },
        "comparison": {"kind": "rule"},
    }

    llm_data = {
        "paths": {"summary": "llm/summary.json", "comparison": "llm/comparison.json"},
        "summary": {
            "summary": {
                "lifecycle": {
                    "throughput_rps": "3.0±0.0",
                    "latency_p95_ms": "120.0±0.0",
                }
            }
        },
        "comparison": {"kind": "llm"},
    }

    result = evidence._build_side_by_side(rule_data, llm_data, "demo_cpu", "run123")

    assert result["run_id"] == "run123"
    assert result["scenario"] == "demo_cpu"
    assert result["metric_basis"] == "normalized_canonical"
    assert result["deltas"]["throughput_rps"]["rule"] == pytest.approx(2.0)
    assert result["deltas"]["throughput_rps"]["llm"] == pytest.approx(3.0)
    assert result["deltas"]["throughput_rps"]["delta_pct_vs_rule"] == pytest.approx(50.0)
    assert "cpu_pct" in result["excluded_metrics"]


def test_run_mode_builds_demo_runner_command_with_correct_agent_url(tmp_path: Path):
    captured = {}

    class Proc:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_set_mode(mode):
        captured["mode"] = mode

    def fake_run_cmd(cmd, check=False):
        captured["cmd"] = cmd
        return Proc()

    with patch("run_rule_llm_evidence.set_agent_mode", side_effect=fake_set_mode):
        with patch("run_rule_llm_evidence._run_cmd", side_effect=fake_run_cmd):
            evidence.run_mode(
                mode="rule",
                scenario="demo_cpu",
                iterations=1,
                duration=60,
                mode_results_dir=tmp_path / "rule",
                target_url="http://localhost:5000",
                prometheus_url="http://localhost:9090",
                llm_agent_url="http://localhost:8083",
                rule_agent_url="http://localhost:5001",
            )

    assert captured["mode"] == "rule"
    cmd = captured["cmd"]
    assert "--scenario" in cmd and "demo_cpu" in cmd
    assert "--agent-url" in cmd and "http://localhost:5001" in cmd


def test_run_mode_raises_when_demo_runner_fails(tmp_path: Path):
    class Proc:
        returncode = 2
        stdout = "bad"
        stderr = "worse"

    with patch("run_rule_llm_evidence.set_agent_mode"):
        with patch("run_rule_llm_evidence._run_cmd", return_value=Proc()):
            with pytest.raises(RuntimeError):
                evidence.run_mode(
                    mode="llm",
                    scenario="demo_cpu",
                    iterations=1,
                    duration=60,
                    mode_results_dir=tmp_path / "llm",
                    target_url=None,
                    prometheus_url=None,
                    llm_agent_url="http://localhost:8083",
                    rule_agent_url="http://localhost:5001",
                )


def test_main_restores_agents_and_writes_consolidated_json(tmp_path: Path):
    run_root = tmp_path / "evidence"
    run_id = "fixed_run"

    llm_scenario_dir = run_root / run_id / "llm" / "demo_cpu"
    rule_scenario_dir = run_root / run_id / "rule" / "demo_cpu"
    llm_scenario_dir.mkdir(parents=True)
    rule_scenario_dir.mkdir(parents=True)

    llm_summary = {"summary": {"lifecycle": {"throughput_rps": "3.0±0.0"}}}
    rule_summary = {"summary": {"lifecycle": {"throughput_rps": "2.0±0.0"}}}

    (llm_scenario_dir / "summary.json").write_text(json.dumps(llm_summary), encoding="utf-8")
    (llm_scenario_dir / "comparison.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    (rule_scenario_dir / "summary.json").write_text(json.dumps(rule_summary), encoding="utf-8")
    (rule_scenario_dir / "comparison.json").write_text(json.dumps({"b": 2}), encoding="utf-8")

    argv = [
        "prog",
        "--scenario", "demo_cpu",
        "--results-root", str(run_root),
        "--run-id", run_id,
    ]

    with patch("run_rule_llm_evidence.sys.argv", argv):
        with patch("run_rule_llm_evidence.run_mode"):
            with patch("run_rule_llm_evidence.restore_agents") as restore_mock:
                evidence.main()

    restore_mock.assert_called_once()
    consolidated = run_root / run_id / "comparison" / "rule_vs_llm_demo_cpu.json"
    assert consolidated.exists()

    data = json.loads(consolidated.read_text(encoding="utf-8"))
    assert data["run_id"] == run_id
    assert data["scenario"] == "demo_cpu"
    assert data["deltas"]["throughput_rps"]["rule"] == pytest.approx(2.0)
    assert data["deltas"]["throughput_rps"]["llm"] == pytest.approx(3.0)
