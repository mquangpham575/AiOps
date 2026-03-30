import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))

import pytest
from unittest.mock import patch, MagicMock
import json


def _make_prom_response(value):
    """Helper: fake Prometheus instant query JSON response."""
    return {"status": "success", "data": {"result": [{"metric": {}, "value": [0, str(value)]}]}}


def _make_alert(alertname="HighCPUUsage", scenario="cpu_stress", severity="critical"):
    return {
        "labels": {"alertname": alertname, "severity": severity, "scenario": scenario},
        "annotations": {"summary": "CPU qua tai", "description": "CPU: 94%"},
        "status": "firing",
        "startsAt": "2026-03-30T14:00:00Z",
    }


@pytest.fixture
def agent_module():
    import agent
    return agent


def test_enrich_alert_context_cpu(agent_module):
    """CPU stress alert fetches cpu_pct, load1, load5, container_cpu."""
    mock_get = MagicMock()
    mock_get.return_value.json.side_effect = [
        _make_prom_response(94.2),   # cpu_pct
        _make_prom_response(3.8),    # load1
        _make_prom_response(2.1),    # load5
        _make_prom_response(91.0),   # container_cpu
    ]
    with patch("agent._requests.get", mock_get):
        ctx = agent_module.enrich_alert_context(_make_alert(scenario="cpu_stress"))

    assert ctx["cpu_pct"] == pytest.approx(94.2)
    assert ctx["load1"] == pytest.approx(3.8)
    assert ctx["container_cpu"] == pytest.approx(91.0)


def test_enrich_alert_context_ddos(agent_module):
    """DDoS alert fetches req_rate, latency_ms (converted from seconds), network_bytes."""
    mock_get = MagicMock()
    mock_get.return_value.json.side_effect = [
        _make_prom_response(847.0),   # req_rate
        _make_prom_response(2.34),    # latency_s → converted to ms
        _make_prom_response(1048576), # network_bytes
    ]
    with patch("agent._requests.get", mock_get):
        ctx = agent_module.enrich_alert_context(_make_alert(alertname="HighRequestRate", scenario="ddos"))

    assert ctx["req_rate"] == pytest.approx(847.0)
    assert ctx["latency_ms"] == pytest.approx(2340.0)


def test_enrich_alert_context_memory(agent_module):
    """Memory stress alert fetches memory_pct, memory_available_mb, container_memory_mb."""
    mock_get = MagicMock()
    mock_get.return_value.json.side_effect = [
        _make_prom_response(88.0),                  # memory_pct
        _make_prom_response(210 * 1024 * 1024),     # available bytes → MB
        _make_prom_response(195 * 1024 * 1024),     # container memory bytes → MB
    ]
    with patch("agent._requests.get", mock_get):
        ctx = agent_module.enrich_alert_context(_make_alert(scenario="memory_stress"))

    assert ctx["memory_pct"] == pytest.approx(88.0)
    assert ctx["memory_available_mb"] == pytest.approx(210.0, abs=1.0)


def test_enrich_alert_context_prometheus_timeout(agent_module):
    """Returns N/A fallback for all metrics if Prometheus is unreachable."""
    with patch("agent._requests.get", side_effect=Exception("timeout")):
        ctx = agent_module.enrich_alert_context(_make_alert(scenario="cpu_stress"))

    assert ctx["cpu_pct"] == "N/A"
    assert ctx["load1"] == "N/A"


def test_build_prompt_contains_metrics(agent_module):
    """build_prompt includes real metric values in the returned string."""
    alert = _make_alert()
    ctx = {"cpu_pct": 94.2, "load1": 3.8, "load5": 2.1, "container_cpu": 91.0}
    prompt = agent_module.build_prompt(alert, ctx)

    assert "94.2" in prompt
    assert "3.8" in prompt
    assert "HighCPUUsage" in prompt
    assert "cpu_stress" in prompt


def test_build_prompt_no_hardcoded_action(agent_module):
    """build_prompt must NOT hardcode the expected action in the user-facing prompt."""
    alert = _make_alert()
    ctx = {"cpu_pct": 94.2, "load1": 3.8}
    prompt = agent_module.build_prompt(alert, ctx)

    # The prompt should NOT give away the answer as a hardcoded JSON
    assert '"action": "auto_kill_cpu_stress"' not in prompt
