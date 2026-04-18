"""
rule-based-agent — Deterministic baseline agent for MTTR comparison.

No LLM. Alert → lookup rule table → execute action → record metrics.

Endpoints:
  POST /alert    <- AlertManager webhook (same payload schema as AI agent)
  GET  /health   <- health check
  GET  /logs     <- recent action log (for demo)
  GET  /metrics  <- Prometheus metrics
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone
from collections import deque
import threading
import subprocess
import hmac
from flask import Flask, request, jsonify
from prometheus_client import Gauge, Counter

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Flask ────────────────────────────────────────────────────
app = Flask(__name__)
try:
    from prometheus_flask_exporter import PrometheusMetrics
    PrometheusMetrics(app)
    logger.info("Prometheus metrics enabled")
except Exception as e:
    logger.warning(f"Prometheus exporter skipped: {e}")
    from flask import Response
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    @app.route("/metrics")
    def metrics():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

# ── MTTR Prometheus gauges ───────────────────────────────────
AGENT_RESPONSE_LATENCY = Gauge(
    "agent_response_latency_seconds",
    "Time from webhook received to action taken",
    ["agent_type"],
)
AGENT_MTTR = Gauge(
    "agent_mttr_seconds",
    "End-to-end incident response time (alert startsAt to action taken)",
    ["agent_type"],
)

# AGENT_REMEDIATION_COUNT: Theo dõi số lượng hành động remediation
AGENT_REMEDIATION_COUNT = Counter(
    "agent_remediation_count_total",
    "Total count of remediation actions taken by the agent",
    ["agent_type", "status"],
)

# Khởi tạo giá trị 0 cho labels để tránh 'No Data' trên dashboard
AGENT_RESPONSE_LATENCY.labels(agent_type="rule").set(0)
AGENT_MTTR.labels(agent_type="rule").set(0)
AGENT_REMEDIATION_COUNT.labels(agent_type="rule", status="success").inc(0)
AGENT_REMEDIATION_COUNT.labels(agent_type="rule", status="failure").inc(0)
AGENT_REMEDIATION_COUNT.labels(agent_type="rule", status="resolved").inc(0)
AGENT_REMEDIATION_COUNT.labels(agent_type="rule", status="monitoring").inc(0)

# ── SSH Remote Execution ──────────────────────────────────────
REMOTE_IP = os.environ.get("AZURE_APP_IP", "10.0.1.6")
SSH_USER = os.environ.get("SSH_USER", "azureuser")
SSH_PORT = os.environ.get("SSH_PORT", "22")
DEFAULT_CONTAINER = os.environ.get("TARGET_CONTAINER_NAME", "target-app")

def _run_remote_docker(command: str) -> str:
    """Helper to run a docker command on the remote App node via SSH."""
    key_path = "/root/.ssh/id_rsa"
    temp_key = "/tmp/id_rsa_rule"
    
    try:
        if os.path.exists(key_path):
            # Permission hardening: SSH strictly requires 600 permissions.
            subprocess.run(["cp", key_path, temp_key], check=True, capture_output=True)
            subprocess.run(["chmod", "600", temp_key], check=True, capture_output=True)
            use_key = temp_key
        else:
            use_key = key_path # Fallback
    except Exception as e:
        logger.warning(f"Failed to harden SSH key permissions: {e}")
        use_key = key_path

    ssh_cmd = [
        "ssh", "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-p", SSH_PORT,
        "-i", use_key,
        f"{SSH_USER}@{REMOTE_IP}",
        f"sudo docker {command}"
    ]
    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return f"ERROR (code {result.returncode}): {result.stderr or result.stdout}"
        return result.stdout.strip()
    except Exception as e:
        return f"SSH ERROR: {e}"


# ── Rule table ───────────────────────────────────────────────
RULE_TABLE = {
    "ContainerHighCPU":        "restart_service",
    "HighCPUUsage":            "restart_service",
    "HighMemoryUsage":         "restart_service",
    "CriticalSystemLoad":      "restart_service",
    "HighSystemLoad":          "reduce_system_load",
    "HighRequestLatency":      "log_only",
    "HighRequestRate":         "log_only",
    "HighContainerRestartRate": "log_only",
}
DEFAULT_ACTION = "log_only"


# ── Idempotency cooldown ────────────────────────────────────
_cooldown: dict[str, float] = {}
_cooldown_lock = threading.Lock()

def _cleanup_cooldown():
    """Periodic cleanup of old cooldown entries"""
    now = time.time()
    for k in list(_cooldown.keys()):
        if now - _cooldown.get(k, 0) > 60:
            _cooldown.pop(k, None)

def is_on_cooldown(key: str, ttl: int = 30) -> bool:
    with _cooldown_lock:
        return time.time() - _cooldown.get(key, 0) < ttl


def set_cooldown(key: str):
    with _cooldown_lock:
        _cooldown[key] = time.time()
        # Periodically clean up dictionary to prevent unbounded growth
        if len(_cooldown) > 100:
            _cleanup_cooldown()


# ── Action executors ─────────────────────────────────────────
def restart_service(container_name: str = None) -> str:
    if container_name is None:
        container_name = DEFAULT_CONTAINER
    try:
        output = _run_remote_docker(f"restart {container_name}")
        if "ERROR" in output:
            logger.error(f"[restart_service] {output}")
            return output
        msg = f"Restarted container remotely: {container_name}"
        logger.info(f"[restart_service] {msg}")
        return msg
    except Exception as e:
        logger.error(f"[restart_service] Error: {e}")
        return f"ERROR: {e}"


def reduce_system_load() -> str:
    try:
        output = _run_remote_docker(f"restart {DEFAULT_CONTAINER}")
        if "ERROR" in output:
            logger.error(f"[reduce_system_load] {output}")
            return output
        msg = f"Restarted {DEFAULT_CONTAINER} remotely to reduce load"
        logger.info(f"[reduce_system_load] {msg}")
        return msg
    except Exception as e:
        logger.error(f"[reduce_system_load] Error: {e}")
        return f"ERROR: {e}"


ACTIONS = {
    "restart_service":    restart_service,
    "reduce_system_load": reduce_system_load,
}


# ── Action executor auth ─────────────────────────────────────
AGENT_API_KEY = os.environ.get("AGENT_API_KEY", "")

def require_api_key(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        provided = request.headers.get("X-Agent-Key", "") or request.args.get("api_key", "")
        auth_header = request.headers.get("Authorization", "")
        if not provided and auth_header.startswith("Bearer "):
            provided = auth_header.split(" ")[-1]
        if not AGENT_API_KEY or not hmac.compare_digest(provided, AGENT_API_KEY):
            logger.warning("Unauthorized access attempt to rule-based agent")
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# ── Action log ───────────────────────────────────────────────
action_log = deque(maxlen=100)

# ── Webhook endpoint ─────────────────────────────────────────
@app.route("/alert", methods=["POST"])
@require_api_key
def alert_webhook():
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "Invalid JSON"}), 400

    alerts = payload.get("alerts", [])
    if not alerts:
        return jsonify({"warning": "No alerts"}), 200

    logger.info(f"Received {len(alerts)} alert(s)")
    results = []

    for alert in alerts:
        webhook_received_at = datetime.now(timezone.utc)
        labels = alert.get("labels", {})
        alertname = labels.get("alertname", "Unknown")
        scenario = labels.get("scenario", "unknown")
        status = alert.get("status", "firing")

        logger.info(f"--- Processing: {alertname} [{scenario}] [{status}] ---")

        if status == "resolved":
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "webhook_received_at": webhook_received_at.isoformat(),
                "alert": alertname,
                "scenario": scenario,
                "action": None,
                "result": "Alert resolved, no action needed.",
                "latency_ms": 0,
            }
            action_log.append(entry)
            AGENT_REMEDIATION_COUNT.labels(agent_type="rule", status="resolved").inc()
            results.append(entry)
            continue

        # Lookup action
        action_name = RULE_TABLE.get(alertname, DEFAULT_ACTION)
        cooldown_key = f"{alertname}:{DEFAULT_CONTAINER}"

        if action_name != "log_only" and is_on_cooldown(cooldown_key):
            logger.info(f"Cooldown active for {cooldown_key}, skipping {action_name}")
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "webhook_received_at": webhook_received_at.isoformat(),
                "alert": alertname,
                "scenario": scenario,
                "action": f"{action_name} (cooldown)",
                "result": "Skipped — cooldown active",
                "latency_ms": 0,
            }
            action_log.append(entry)
            results.append(entry)
            continue

        # Execute action
        if action_name in ACTIONS:
            tool_result = ACTIONS[action_name]()
            set_cooldown(cooldown_key)
        else:
            tool_result = f"Logged alert {alertname} — no remediation defined"
            AGENT_REMEDIATION_COUNT.labels(agent_type="rule", status="monitoring").inc()

        action_taken_at = datetime.now(timezone.utc)

        # ── Record MTTR metrics ──────────────────────────────
        response_latency = (action_taken_at - webhook_received_at).total_seconds()
        AGENT_RESPONSE_LATENCY.labels(agent_type="rule").set(response_latency)
        
        # Track success/failure only if an action was actually taken
        if action_name in ACTIONS:
            if tool_result and "ERROR" not in str(tool_result).upper():
                AGENT_REMEDIATION_COUNT.labels(agent_type="rule", status="success").inc()
            else:
                AGENT_REMEDIATION_COUNT.labels(agent_type="rule", status="failure").inc()

        mttr = None
        try:
            starts_at_raw = alert.get("startsAt", "")
            if starts_at_raw:
                t_start = datetime.fromisoformat(starts_at_raw.replace("Z", "+00:00"))
                mttr = (action_taken_at - t_start).total_seconds()
                AGENT_MTTR.labels(agent_type="rule").set(mttr)
        except Exception:
            pass

        entry = {
            "timestamp": action_taken_at.isoformat(),
            "webhook_received_at": webhook_received_at.isoformat(),
            "alert": alertname,
            "scenario": scenario,
            "action": action_name,
            "result": tool_result,
            "latency_ms": round(response_latency * 1000, 1),
            "response_latency_s": round(response_latency, 3),
            "mttr_s": round(mttr, 3) if mttr is not None else None,
        }
        action_log.append(entry)
        results.append(entry)

    return jsonify(results), 200


@app.route("/health")
def health():
    return jsonify({"status": "ok", "agent_type": "rule-based", "actions_logged": len(action_log)})


@app.route("/logs")
@require_api_key
def logs():
    try:
        limit = min(int(request.args.get("limit", 50)), 100)
    except (ValueError, TypeError):
        limit = 50
    return jsonify(list(action_log)[-limit:])


if __name__ == "__main__":
    if not AGENT_API_KEY or AGENT_API_KEY == "your_secret_agent_key_here":
        logger.critical("AGENT_API_KEY not set or using default value! Agent must be secured to start.")
        sys.exit(1)
    logger.info("Rule-Based Agent starting on port 5001...")
    app.run(host="0.0.0.0", port=5001, threaded=True, debug=False)
