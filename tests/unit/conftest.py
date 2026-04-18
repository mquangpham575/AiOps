import os
import sys


# Centralize path setup to avoid "Nghi-Thuc services/" drift
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# Order matters: last insert at 0 wins.
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
sys.path.insert(0, os.path.join(BASE_DIR, "src", "app", "target-app"))
sys.path.insert(0, os.path.join(BASE_DIR, "src", "agent", "rule-based-agent"))
sys.path.insert(0, os.path.join(BASE_DIR, "src", "agent", "ai-agent")) # AI Agent should win by default

# Set required env vars before any agent module is imported
os.environ.setdefault("GEMINI_API_KEY", "test-fake-key-for-unit-tests")
os.environ.setdefault("AGENT_API_KEY", "test-agent-key-12345")
os.environ.setdefault("GRAFANA_URL", "http://localhost:3000")
os.environ.setdefault("GRAFANA_TOKEN", "test-grafana-token")
os.environ.setdefault("PROMETHEUS_URL", "http://localhost:9090")
os.environ.setdefault("MEMORY_HOLD_SECONDS", "0")  # no sleep in unit tests
