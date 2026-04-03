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
import time
import logging
from datetime import datetime, timezone

import docker
from flask import Flask, request, jsonify
from prometheus_client import Gauge

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
    from prometheus_flask_exporter import PrometheusFlaskExporter
    PrometheusFlaskExporter(app)
    logger.info("Prometheus metrics enabled")
except Exception as e:
    logger.warning(f"Prometheus exporter skipped: {e}")
    from flask import Response
    @app.route("/metrics")
    def metrics():
        return Response("# Rule-based agent metrics (fallback)\n", mimetype="text/plain")

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

# ── Docker client ────────────────────────────────────────────
_docker_client = None
DEFAULT_CONTAINER = os.environ.get("TARGET_CONTAINER_NAME", "target-app")


def _get_docker():
    global _docker_client
    if _docker_client is None:
        _docker_client = docker.from_env()
    return _docker_client


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


def is_on_cooldown(key: str, ttl: int = 30) -> bool:
    return time.time() - _cooldown.get(key, 0) < ttl


def set_cooldown(key: str):
    _cooldown[key] = time.time()


# ── Action executors ─────────────────────────────────────────
def restart_service(container_name: str = None) -> str:
    if container_name is None:
        container_name = DEFAULT_CONTAINER
    try:
        client = _get_docker()
        container = client.containers.get(container_name)
        container.restart(timeout=10)
        msg = f"Restarted container: {container_name}"
        logger.info(f"[restart_service] {msg}")
        return msg
    except Exception as e:
        logger.error(f"[restart_service] Error: {e}")
        return f"ERROR: {e}"


def reduce_system_load() -> str:
    try:
        client = _get_docker()
        container = client.containers.get(DEFAULT_CONTAINER)
        container.restart(timeout=10)
        msg = f"Restarted {DEFAULT_CONTAINER} to reduce load"
        logger.info(f"[reduce_system_load] {msg}")
        return msg
    except Exception as e:
        logger.error(f"[reduce_system_load] Error: {e}")
        return f"ERROR: {e}"


ACTIONS = {
    "restart_service":    restart_service,
    "reduce_system_load": reduce_system_load,
}


# ── Action log ───────────────────────────────────────────────
action_log: list[dict] = []


# ── Webhook endpoint ─────────────────────────────────────────
@app.route("/alert", methods=["POST"])
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

        action_taken_at = datetime.now(timezone.utc)

        # ── Record MTTR metrics ──────────────────────────────
        response_latency = (action_taken_at - webhook_received_at).total_seconds()
        AGENT_RESPONSE_LATENCY.labels(agent_type="rule").set(response_latency)

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
        if len(action_log) > 100:
            action_log.pop(0)
        results.append(entry)

    return jsonify(results), 200


@app.route("/health")
def health():
    return jsonify({"status": "ok", "agent_type": "rule-based", "actions_logged": len(action_log)})


@app.route("/logs")
def logs():
    limit = int(request.args.get("limit", 50))
    return jsonify(action_log[-limit:])


if __name__ == "__main__":
    logger.info("Rule-Based Agent starting on port 5001...")
    app.run(host="0.0.0.0", port=5001, threaded=True, debug=False)
