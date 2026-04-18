from unittest.mock import patch, MagicMock
import tools


def test_post_grafana_annotation_success():
    """Posts annotation to Grafana and returns success message."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("tools.requests.post", return_value=mock_response) as mock_post:
        result = tools.post_grafana_annotation(
            text="🤖 restart_service — ddos | CPU:45% MEM:60% LAT:2300ms",
            tags=["aiops", "auto-remediation", "ddos"]
        )

    assert "OK" in result or "200" in result
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "annotations" in call_kwargs[0][0]  # URL contains /api/annotations
    payload = call_kwargs[1]["json"]
    assert payload["text"] == "🤖 restart_service — ddos | CPU:45% MEM:60% LAT:2300ms"
    assert "aiops" in payload["tags"]


def test_post_grafana_annotation_no_token(monkeypatch):
    """Returns skip message when GRAFANA_TOKEN is not set."""
    monkeypatch.setattr(tools, "GRAFANA_TOKEN", "")

    with patch("tools.requests.post") as mock_post:
        result = tools.post_grafana_annotation("test", ["tag"])

    assert "skipped" in result.lower() or "no token" in result.lower()
    mock_post.assert_not_called()


def test_post_grafana_annotation_failure(monkeypatch):
    """Returns error message but does not raise when Grafana is unreachable."""
    monkeypatch.setattr(tools, "GRAFANA_TOKEN", "fake-token-for-failure-test")

    with patch("tools.requests.post", side_effect=Exception("connection refused")):
        result = tools.post_grafana_annotation("test", ["tag"])

    assert "ERROR" in result or "error" in result.lower()
    # Must not raise — Grafana failure is non-fatal


def test_utility_tools_not_in_agent_tools():
    """get_prometheus_metrics is now an AI-callable tool.
    validate_container_exists remains an internal utility."""
    import tools
    assert "get_prometheus_metrics" in tools.TOOLS
    assert "validate_container_exists" not in tools.TOOLS
    # Confirm the functions still exist as utilities
    assert callable(tools.get_prometheus_metrics)
    assert callable(tools.validate_container_exists)


def test_removed_tools_not_in_agent_tools():
    """block_ip and apply_rate_limit were removed for the distributed setup."""
    assert "block_ip" not in tools.TOOLS
    assert "apply_rate_limit" not in tools.TOOLS
