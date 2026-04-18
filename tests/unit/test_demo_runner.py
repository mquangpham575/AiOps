import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import demo_runner  # type: ignore
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


def _make_prom_response(value):
    return {"status": "success", "data": {"result": [{"metric": {}, "value": [0, str(value)]}]}}


def _make_alerts_response(alertname: str, active_at: str, state: str = "firing") -> dict:
    """Helper: fake Prometheus /api/v1/alerts response."""
    return {
        "data": {
            "alerts": [{
                "labels": {"alertname": alertname},
                "state": state,
                "activeAt": active_at,
            }]
        }
    }


@pytest.fixture
def runner():
    config = {
        "defaults": {"iterations": 1, "duration": 10, "cooldown": 0, "cooldown_between": 0},
        "scenarios": {},
    }
    return demo_runner.DemoRunner(
        config=config,
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


# ── wait_for_alert_fired ───────────────────────────────────────────────────

def test_wait_for_alert_fired_found(runner):
    """Returns activeAt datetime when matching alert appears in firing state after `after`."""
    after = datetime(2026, 4, 2, 10, 0, 0, tzinfo=timezone.utc)
    mock_resp = MagicMock()
    mock_resp.json.return_value = _make_alerts_response(
        "HighRequestLatency", "2026-04-02T10:00:08+00:00"
    )

    with patch("demo_runner.requests.get", return_value=mock_resp):
        result = runner.wait_for_alert_fired(
            ["HighRequestLatency", "HighRequestRate"], after=after
        )

    assert result is not None
    assert result == datetime(2026, 4, 2, 10, 0, 8, tzinfo=timezone.utc)


def test_wait_for_alert_fired_ignores_old_alert(runner):
    """Returns None when the alert's activeAt is before `after` (pre-existing alert)."""
    after = datetime(2026, 4, 2, 10, 0, 0, tzinfo=timezone.utc)
    mock_resp = MagicMock()
    mock_resp.json.return_value = _make_alerts_response(
        "HighRequestLatency", "2026-04-02T09:55:00+00:00"  # fires before our attack
    )

    with patch("demo_runner.requests.get", return_value=mock_resp):
        with patch.object(demo_runner, "SCENARIO_TIMEOUT_S", 0):
            result = runner.wait_for_alert_fired(["HighRequestLatency"], after=after)

    assert result is None


def test_wait_for_alert_fired_timeout(runner):
    """Returns None when no alert fires within timeout."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"alerts": []}}

    with patch("demo_runner.requests.get", return_value=mock_resp):
        with patch.object(demo_runner, "SCENARIO_TIMEOUT_S", 0):
            result = runner.wait_for_alert_fired(
                ["HighRequestLatency"], after=datetime.now(timezone.utc)
            )

    assert result is None


# ── wait_for_recovery ─────────────────────────────────────────────────────

def test_wait_for_recovery_requires_consecutive(runner):
    """Single dip below threshold does NOT declare recovery; 3 consecutive polls do."""
    # Values: above, below (bounce), above, below, below, below (3 consecutive → recovery)
    values = [80.0, 20.0, 80.0, 20.0, 20.0, 20.0]
    call_count = 0

    def mock_get(url, params=None, timeout=None):
        nonlocal call_count
        resp = MagicMock()
        resp.json.return_value = _make_prom_response(values[min(call_count, len(values) - 1)])
        call_count += 1
        return resp

    with patch("demo_runner.requests.get", side_effect=mock_get):
        with patch("demo_runner.PROM_POLL_S", 0):
            result = runner.wait_for_recovery(
                "100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)",
                threshold=30.0,
            )

    assert result is not None
    # Must have polled at least 6 times (2 bounces + 3 consecutive + initial above)
    assert call_count >= 6


def test_wait_for_recovery_timeout(runner):
    """Returns None when metric never sustains below threshold within timeout."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = _make_prom_response(95.0)  # always above threshold

    with patch("demo_runner.requests.get", return_value=mock_resp):
        with patch("demo_runner.SCENARIO_TIMEOUT_S", 0):
            result = runner.wait_for_recovery(
                "100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)",
                threshold=30.0,
            )

    assert result is None


# ── export_csv ────────────────────────────────────────────────────────────

def test_export_csv(runner, tmp_path):
    """export_csv writes the unified CSV schema used by the new runner."""
    runner.export_file = str(tmp_path / "results.csv")
    runner.results = [{
        "scenario": "throughput",
        "iteration": 1,
        "phase": "baseline",
        "latency_p50_ms": 12.3,
        "latency_p95_ms": 45.1,
        "latency_p99_ms": 120.5,
        "throughput_rps": 150.2,
        "error_rate_pct": 0.1,
        "cpu_pct": 15.3,
        "memory_pct": 42.1,
        "agent_cpu_pct": 1.2,
        "agent_memory_mb": 180.0,
    }]
    runner.export_csv()

    content = open(runner.export_file).read()
    # Header contains unified fields
    assert "scenario" in content
    assert "iteration" in content
    assert "phase" in content
    assert "latency_p50_ms" in content
    assert "throughput_rps" in content
    # Values written correctly
    assert "throughput" in content
    assert "baseline" in content
    assert "150.2" in content

