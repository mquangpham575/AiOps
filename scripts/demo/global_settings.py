import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# This file is in 'scripts/demo/', so its parent.parent.parent is the ROOT_DIR
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = ROOT_DIR / "tests" / "performance" / "scenarios.yml"
RESULTS_DIR = ROOT_DIR / "results"

# ── Environment-based service URLs ───────────────────────────────────────────
_azure_app_ip = os.environ.get("AZURE_VM_IP") or os.environ.get("AZURE_APP_IP")
_azure_control_ip = (
    os.environ.get("AZURE_CONTROL_IP")
    or os.environ.get("AZURE_VM_IP")
    or os.environ.get("AZURE_APP_IP")
)
_default_target = f"http://{_azure_app_ip}:80" if _azure_app_ip else "http://localhost:5000"

# Service Endpoints
TARGET_URL = os.environ.get("TARGET_URL", _default_target)
AGENT_URL = os.environ.get(
    "AGENT_URL",
    f"http://{_azure_control_ip}:8083" if _azure_control_ip else "http://localhost:8083",
)
PROMETHEUS_URL = os.environ.get(
    "PROMETHEUS_URL",
    f"http://{_azure_control_ip}:9090" if _azure_control_ip else "http://localhost:9090",
)

# Authentication & Credentials
AGENT_KEY = os.environ.get("AGENT_API_KEY", "")
SSH_KEY_PATH = ROOT_DIR / ".ssh" / "aiops3_key_rsa"

# Polling & Timeout Settings
PROM_POLL_S = 1
SCENARIO_TIMEOUT_S = 120
POLL_INTERVAL_S = 1

def resolve_docker_host() -> str | None:
    """Determine the DOCKER_HOST based on the environment."""
    explicit = os.environ.get("DOCKER_HOST")
    if explicit:
        return explicit
    if _azure_app_ip:
        # Assuming we use a tunnel or direct access on the VM
        return "tcp://localhost:2375"
    return None
