import pytest
from unittest.mock import patch, MagicMock


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
    import sys
    if "ai_agent" in sys.modules:
        del sys.modules["ai_agent"]
    import ai_agent  # type: ignore
    return ai_agent


def test_enrich_alert_context_cpu(agent_module):
    """CPU stress alert fetches cpu_pct, load1, load5, container_cpu."""
    mock_get = MagicMock()
    mock_get.return_value.json.side_effect = [
        _make_prom_response(94.2),   # cpu_pct
        _make_prom_response(3.8),    # load1
        _make_prom_response(2.1),    # load5
        _make_prom_response(91.0),   # container_cpu
    ]
    with patch("ai_agent.requests.get", mock_get):
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
    with patch("ai_agent.requests.get", mock_get):
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
    with patch("ai_agent.requests.get", mock_get):
        ctx = agent_module.enrich_alert_context(_make_alert(scenario="memory_stress"))

    assert ctx["memory_pct"] == pytest.approx(88.0)
    assert ctx["memory_available_mb"] == pytest.approx(210.0, abs=1.0)


def test_enrich_alert_context_prometheus_timeout(agent_module):
    """Returns N/A fallback for all metrics if Prometheus is unreachable."""
    with patch("ai_agent.requests.get", side_effect=Exception("timeout")):
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


def test_webhook_two_phase_pipeline(agent_module):
    """webhook() calls enrich_alert_context before build_prompt (two-phase pipeline)."""

    payload = {
        "alerts": [{
            "labels": {"alertname": "HighCPUUsage", "severity": "critical", "scenario": "cpu_stress"},
            "annotations": {"summary": "CPU qua tai", "description": "CPU: 94%"},
            "status": "firing",
            "startsAt": "2026-03-30T14:00:00Z",
        }]
    }

    mock_decision = {
        "reasoning": "CPU=94.2% with load1=3.8 — kill stress process",
        "action": "auto_kill_cpu_stress",
        "params": {"container_name": "target-app", "cpu_threshold": 80.0},
        "confidence": 0.95,
    }

    with (
        patch("ai_agent.enrich_alert_context", return_value={"cpu_pct": 94.2, "load1": 3.8}) as mock_enrich,
        patch("ai_agent.call_gemini", return_value=(mock_decision, 1.4)) as mock_gemini,
        patch("ai_agent.TOOLS", {"auto_kill_cpu_stress": MagicMock(return_value="Killed 2 processes")}),
        patch("ai_agent.post_grafana_annotation", return_value="OK"),
    ):
        with agent_module.app.test_client() as client:
            resp = client.post(
                "/webhook",
                json=payload,
                headers={"X-Agent-Key": "test-agent-key-12345"},
            )

    assert resp.status_code == 200
    mock_enrich.assert_called_once()          # Phase 1 was called
    mock_gemini.assert_called_once()          # Phase 2 was called
    data = resp.get_json()
    assert len(data) == 1
    entry = data[0]
    assert entry["action"] == "auto_kill_cpu_stress"
    assert "webhook_received_at" in entry     # MTTR timestamp present
    assert entry["llm_latency_s"] == pytest.approx(1.4)


def test_webhook_mttr_field_present(agent_module):
    """Each action_log entry includes webhook_received_at for MTTR calculation."""
    payload = {
        "alerts": [{
            "labels": {"alertname": "HighRequestRate", "severity": "warning", "scenario": "ddos"},
            "annotations": {"summary": "Request rate too high", "description": ""},
            "status": "firing",
            "startsAt": "2026-03-30T14:00:00Z",
        }]
    }
    mock_decision = {"reasoning": "DDoS detected", "action": "restart_service",
                     "params": {"container_name": "target-app"}, "confidence": 0.9}

    with (
        patch("ai_agent.enrich_alert_context", return_value={"req_rate": 847.0, "latency_ms": 2100.0}),
        patch("ai_agent.call_gemini", return_value=(mock_decision, 2.1)),
        patch("ai_agent.TOOLS", {"restart_service": MagicMock(return_value="Restarted container: target-app")}),
        patch("ai_agent.post_grafana_annotation", return_value="OK"),
    ):
        with agent_module.app.test_client() as client:
            resp = client.post(
                "/webhook",
                json=payload,
                headers={"X-Agent-Key": "test-agent-key-12345"},
            )

    assert resp.status_code == 200
    entry = resp.get_json()[0]
    assert "webhook_received_at" in entry
    assert entry["webhook_received_at"] is not None


def test_logs_ui_returns_html(agent_module):
    """GET /logs/ui returns HTML page with table."""
    # Seed the action log with a known entry
    agent_module.action_log.clear()
    agent_module.action_log.append({
        "timestamp": "2026-03-30T14:28:33+00:00",
        "webhook_received_at": "2026-03-30T14:28:30+00:00",
        "alert": "HighCPUUsage",
        "scenario": "cpu_stress",
        "status": "firing",
        "reasoning": "CPU=94% with load1=3.8",
        "action": "auto_kill_cpu_stress",
        "params": {"container_name": "target-app"},
        "confidence": 0.95,
        "result": "Killed 2 processes",
        "llm_latency_s": 1.8,
    })

    with agent_module.app.test_client() as client:
        resp = client.get("/logs/ui")  # no auth needed — read-only public endpoint

    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")
    body = resp.data.decode("utf-8")
    assert "HighCPUUsage" in body
    assert "auto_kill_cpu_stress" in body
    assert "95%" in body


def test_logs_ui_empty_log(agent_module):
    """GET /logs/ui with empty log returns HTML with 'No actions yet' message."""
    agent_module.action_log.clear()

    with agent_module.app.test_client() as client:
        resp = client.get("/logs/ui")  # no auth needed

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "No actions" in body or "empty" in body.lower() or "<tr>" not in body or "no action" in body.lower()
