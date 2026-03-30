import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


def _make_prom_response(value):
    return {"status": "success", "data": {"result": [{"metric": {}, "value": [0, str(value)]}]}}


@pytest.fixture
def runner():
    import demo_runner
    return demo_runner.DemoRunner(
        target_url="http://localhost:5000",
        agent_url="http://localhost:8080",
        prometheus_url="http://localhost:9090",
        agent_key="test-agent-key-12345",
        export_file="test_results.csv",
    )


def test_preflight_all_healthy(runner):
    """preflight() returns True when all services respond 200."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("demo_runner.requests.get", return_value=mock_resp):
        assert runner.preflight() is True


def test_preflight_service_down(runner):
    """preflight() returns False when any service is unreachable."""
    with patch("demo_runner.requests.get", side_effect=Exception("connection refused")):
        assert runner.preflight() is False


def test_record_baseline(runner):
    """record_baseline() returns cpu_pct, memory_pct, latency_ms."""
    responses = [
        _make_prom_response(45.0),   # cpu_pct
        _make_prom_response(55.0),   # memory_pct
        _make_prom_response(0.25),   # latency_s -> latency_ms = 250.0
    ]
    call_count = 0

    def mock_get(url, params=None, timeout=None):
        nonlocal call_count
        resp = MagicMock()
        resp.json.return_value = responses[min(call_count, 2)]
        call_count += 1
        return resp

    with patch("demo_runner.requests.get", side_effect=mock_get):
        baseline = runner.record_baseline()

    assert "cpu_pct" in baseline
    assert "memory_pct" in baseline
    assert "latency_ms" in baseline
    assert baseline["latency_ms"] == pytest.approx(250.0)


def test_find_agent_action_found(runner):
    """find_agent_action finds the most recent entry after given timestamp with matching scenario."""
    t_start = datetime(2026, 3, 30, 14, 0, 0, tzinfo=timezone.utc)
    logs = [
        {"timestamp": "2026-03-30T13:59:00+00:00", "action": "old_action", "scenario": "cpu_stress"},
        {"timestamp": "2026-03-30T14:00:05+00:00", "action": "auto_kill_cpu_stress",
         "scenario": "cpu_stress", "confidence": 0.94, "llm_latency_s": 1.8},
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = logs

    with patch("demo_runner.requests.get", return_value=mock_resp):
        result = runner.find_agent_action(after=t_start, scenario="cpu_stress")

    assert result is not None
    assert result["action"] == "auto_kill_cpu_stress"


def test_find_agent_action_not_found(runner):
    """find_agent_action returns None when no qualifying entry exists."""
    t_start = datetime(2026, 3, 30, 15, 0, 0, tzinfo=timezone.utc)
    logs = [
        {"timestamp": "2026-03-30T14:00:05+00:00", "action": "auto_kill_cpu_stress", "scenario": "cpu_stress"},
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = logs

    with patch("demo_runner.requests.get", return_value=mock_resp):
        result = runner.find_agent_action(after=t_start, scenario="cpu_stress")

    assert result is None


def test_export_csv(runner, tmp_path):
    """export_csv writes all result fields to CSV."""
    runner.export_file = str(tmp_path / "results.csv")
    runner.results = [{
        "scenario": "ddos",
        "alert_fired_at": "14:28:33",
        "agent_acted_at": "14:28:36",
        "recovered_at": "14:28:55",
        "mttr_s": 22.4,
        "action": "apply_rate_limit",
        "confidence": 0.91,
        "llm_latency_s": 2.3,
        "baseline_cpu_pct": 12.0,
        "peak_cpu_pct": 35.0,
        "baseline_mem_pct": 45.0,
        "peak_mem_pct": 62.0,
    }]
    runner.export_csv()

    content = open(runner.export_file).read()
    assert "ddos" in content
    assert "22.4" in content
    assert "apply_rate_limit" in content
