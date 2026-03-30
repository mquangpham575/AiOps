import os
import pytest

# Set required env vars before any agent module is imported
os.environ.setdefault("GEMINI_API_KEY", "test-fake-key-for-unit-tests")
os.environ.setdefault("AGENT_API_KEY", "test-agent-key-12345")
os.environ.setdefault("GRAFANA_URL", "http://localhost:3000")
os.environ.setdefault("GRAFANA_TOKEN", "test-grafana-token")
os.environ.setdefault("PROMETHEUS_URL", "http://localhost:9090")
os.environ.setdefault("MEMORY_HOLD_SECONDS", "0")  # no sleep in unit tests
