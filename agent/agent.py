"""
agent.py — Agentic AIOps: Webhook receiver + AI reasoning + Auto-remediation.

Flow:
  AlertManager → POST /webhook
  → parse alert payload
  → build context prompt
  → gọi Gemini API (gemma-3-1b-it)
  → parse JSON decision
  → thực thi tool tương ứng
  → ghi log + metrics

Endpoints:
  POST /webhook   ← AlertManager gửi vào đây
  GET  /health    ← health check
  GET  /logs      ← xem 50 action gần nhất (dùng cho video demo)
  GET  /metrics   ← Prometheus metrics của agent
"""

import os
import json
import time
import logging
import hmac
import functools
import sys
from datetime import datetime, timezone
from flask import Flask, request, jsonify
import google.generativeai as genai

from tools import TOOLS, TOOLS_DESCRIPTION, post_grafana_annotation
import requests as _requests  # aliased to avoid collision with tools.requests

# ── Logging setup ────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
DEBUG_MODE = os.environ.get("DEBUG_MODE", "false").lower() == "true"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

if DEBUG_MODE:
    logger.setLevel(logging.DEBUG)
    logging.getLogger("tools").setLevel(logging.DEBUG)
    logger.debug("Debug mode enabled")

logger.info(f"Starting AIOps Agent with log level: {LOG_LEVEL}")

# ── Flask ────────────────────────────────────────────────────
app = Flask(__name__)
try:
    from prometheus_flask_exporter import PrometheusFlaskExporter
    PrometheusFlaskExporter(app)
    logger.info("Prometheus metrics enabled")
except Exception as e:
    logger.warning(f"Prometheus exporter skipped: {e}")
    # Fallback: tạo /metrics endpoint đơn giản
    from flask import Response
    @app.route("/metrics")
    def metrics():
        return Response("# AI Agent metrics (fallback)\n", mimetype="text/plain")

# ── Gemini setup ─────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemma-3-1b-it")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY not set! Agent will run in dry-run mode.")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)

# ── Throttle & Auth ───────────────────────────────────────────
_last_llm_call: float = 0.0
MIN_INTERVAL: float = float(os.environ.get("AI_THROTTLE_INTERVAL", "3.0"))
AGENT_API_KEY = os.environ.get("AGENT_API_KEY", "")

if not AGENT_API_KEY or AGENT_API_KEY == "your_secret_agent_key_here":
    logger.critical("AGENT_API_KEY not set or using default value! Agent must be secured to start.")
    sys.exit(1)

logger.info("API Key authentication enabled for /webhook and /logs")


def require_api_key(f):
    """Decorator to require X-Agent-Key header for access."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        provided = request.headers.get("X-Agent-Key", "")
        # Also support Authorization: Bearer <key> (common in AlertManager/webhooks)
        auth_header = request.headers.get("Authorization", "")
        if not provided and auth_header.startswith("Bearer "):
            provided = auth_header.split(" ")[-1]
        
        # Secure comparison to prevent timing attacks
        if not hmac.compare_digest(provided, AGENT_API_KEY):
            logger.warning(f"Unauthorized access attempt from {repr(request.remote_addr)}")
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# ── Action log: lưu 100 action gần nhất ─────────────────────
action_log: list[dict] = []

# ── Prometheus query map per scenario ────────────────────────
_PROM_QUERIES = {
    "cpu_stress": {
        "cpu_pct":       "100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)",
        "load1":         "node_load1",
        "load5":         "node_load5",
        "container_cpu": "rate(container_cpu_usage_seconds_total{name='target-app'}[1m]) * 100",
    },
    "ddos": {
        "req_rate":      "rate(container_network_receive_packets_total{name='target-app'}[30s])",
        "latency_s":     "rate(flask_http_request_duration_seconds_sum{job='target-app'}[1m]) / rate(flask_http_request_duration_seconds_count{job='target-app'}[1m])",
        "network_bytes": "rate(container_network_receive_bytes_total{name='target-app'}[30s])",
    },
    "memory_stress": {
        "memory_pct":         "(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100",
        "memory_available_b": "node_memory_MemAvailable_bytes",
        "container_memory_b": "container_memory_usage_bytes{name='target-app'}",
    },
    "system_load": {
        "load1":  "node_load1",
        "load5":  "node_load5",
        "load15": "node_load15",
        "procs":  "node_procs_running",
    },
}

_ALERT_SCENARIO_MAP = {
    "HighCPUUsage":       "cpu_stress",
    "ContainerHighCPU":   "cpu_stress",
    "CriticalCPUStress":  "cpu_stress",
    "HighRequestRate":    "ddos",
    "HighRequestLatency": "ddos",
    "HighMemoryUsage":    "memory_stress",
    "HighSystemLoad":     "system_load",
    "CriticalSystemLoad": "system_load",
}


def _prom_query(query: str) -> float | str:
    """Run a single Prometheus instant query. Returns float or 'N/A' on any failure."""
    try:
        resp = _requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=3,
        )
        data = resp.json()
        if data["status"] == "success" and data["data"]["result"]:
            return float(data["data"]["result"][0]["value"][1])
    except Exception as e:
        logger.warning(f"[enrich] Prometheus query failed: {e}")
    return "N/A"


def enrich_alert_context(alert: dict) -> dict:
    """
    Phase 1: Query Prometheus for live metrics relevant to this alert's scenario.
    Returns a flat dict of metric values (floats or 'N/A' on timeout).

    Example:
        ctx = enrich_alert_context({"labels": {"scenario": "cpu_stress"}, ...})
        # ctx == {"cpu_pct": 94.2, "load1": 3.8, "load5": 2.1, "container_cpu": 91.0}
    """
    labels    = alert.get("labels", {})
    scenario  = labels.get("scenario", "")
    alertname = labels.get("alertname", "")

    # Fall back to alertname mapping if scenario label is missing or unknown
    if scenario not in _PROM_QUERIES:
        scenario = _ALERT_SCENARIO_MAP.get(alertname, "")

    queries = _PROM_QUERIES.get(scenario, {})
    ctx: dict = {}

    for key, query in queries.items():
        raw = _prom_query(query)
        # Convert byte-level metrics to MB for readability
        if key in ("memory_available_b", "container_memory_b") and raw != "N/A":
            new_key = key.replace("_b", "_mb")
            ctx[new_key] = round(raw / (1024 * 1024), 1)
        # Convert latency from seconds to milliseconds
        elif key == "latency_s" and raw != "N/A":
            ctx["latency_ms"] = round(raw * 1000, 1)
        else:
            ctx[key] = raw if raw == "N/A" else round(raw, 2)

    logger.info(f"[enrich] scenario={scenario!r} context={ctx}")
    return ctx


# ── System prompt cho AI Agent ───────────────────────────────
SYSTEM_PROMPT = f"""You are an AIOps agent responsible for automated IT infrastructure remediation.
When you receive an alert with live system metrics, analyze the data and choose the most appropriate action.

{TOOLS_DESCRIPTION}

RESPONSE RULES (MANDATORY):
- Respond with ONLY a JSON object — no text before or after.
- Schema: {{"reasoning": "<1-2 sentence analysis of the metrics>", "action": "<tool_name or null>", "params": {{}}, "confidence": <0.0-1.0>}}
- Use null action only if the metrics clearly show the alert has already self-resolved.
- Base your reasoning on the actual metric VALUES provided — mention the numbers.

DECISION GUIDELINES:
- CPU > 80% or load1 > 3.0 with container_cpu > 70%: use auto_kill_cpu_stress
- req_rate spike with latency_ms > 1500: use apply_rate_limit
- memory_pct > 75% or memory_available_mb < 300: use restart_service
- load1 > 4.0 with no clear process cause: use reduce_system_load

IMPORTANT: check_system_load() and reduce_system_load() take NO parameters.
"""


def call_gemini(prompt: str) -> tuple[dict, float]:
    """
    Gọi Gemini API với throttle 3s.
    Trả về (decision_dict, latency_seconds).
    """
    global _last_llm_call

    # Throttle
    wait = MIN_INTERVAL - (time.time() - _last_llm_call)
    if wait > 0:
        logger.info(f"Throttle: chờ {wait:.1f}s trước khi gọi Gemini...")
        time.sleep(wait)

    start = time.time()
    try:
        response = model.generate_content(
            SYSTEM_PROMPT + "\n\n" + prompt,
            generation_config=genai.GenerationConfig(
                max_output_tokens=1024,
                temperature=0.2,   # thấp → output ổn định hơn
            )
        )
        latency = time.time() - start
        _last_llm_call = time.time()

        raw = response.text.strip()
        logger.info(f"Gemini response ({latency:.2f}s): {raw[:200]}")

        # Extract JSON from response (gemma-3-1b-it may include extra text)
        try:
            # Try direct parsing first
            decision = json.loads(raw)
        except json.JSONDecodeError:
            # Try to find JSON block in text
            import re
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                json_text = json_match.group()
                decision = json.loads(json_text)
            else:
                raise json.JSONDecodeError("No JSON found in response", raw, 0)

        return decision, latency

    except json.JSONDecodeError as e:
        latency = time.time() - start
        logger.error(f"JSON parse error: {e}")
        logger.debug(f"Raw response: {response.text[:500]}")
        return {
            "reasoning": f"Parse error: {str(e)[:100]}...",
            "action": None,
            "params": {},
            "confidence": 0.0
        }, latency
    except Exception as e:
        latency = time.time() - start
        error_msg = str(e)
        logger.error(f"Gemini API error: {error_msg}")

        # Categorize common errors
        if "quota" in error_msg.lower() or "rate" in error_msg.lower():
            reasoning = "Rate limit exceeded - will retry later"
        elif "network" in error_msg.lower() or "connection" in error_msg.lower():
            reasoning = "Network connection error"
        elif "authentication" in error_msg.lower() or "401" in error_msg:
            reasoning = "API authentication error - check API key"
        else:
            reasoning = f"API error: {error_msg[:100]}..."

        return {
            "reasoning": reasoning,
            "action": None,
            "params": {},
            "confidence": 0.0
        }, latency


def build_prompt(alert: dict, context: dict | None = None) -> str:
    """Build the user-facing prompt for Gemini, enriched with live metrics.

    Args:
        alert:   AlertManager alert dict with labels, annotations, status
        context: flat dict of live Prometheus metrics from enrich_alert_context()
    """
    alert_name  = alert.get("labels", {}).get("alertname", "Unknown")
    severity    = alert.get("labels", {}).get("severity", "unknown")
    scenario    = alert.get("labels", {}).get("scenario", "unknown")
    summary     = alert.get("annotations", {}).get("summary", "")
    description = alert.get("annotations", {}).get("description", "")
    status      = alert.get("status", "firing")

    if context:
        metrics_lines = "\n".join(f"  {k}: {v}" for k, v in context.items())
        metrics_section = f"\nCurrent system metrics (live from Prometheus):\n{metrics_lines}\n"
    else:
        metrics_section = "\n(No live metrics available — decide based on alert context only)\n"

    return f"""=== CẢNH BÁO HỆ THỐNG ===
Alert name : {alert_name}
Severity   : {severity}
Scenario   : {scenario}
Status     : {status}
Summary    : {summary}
Details    : {description}
{metrics_section}
Analyze the metrics above and choose the single best remediation action.
Respond ONLY with valid JSON matching the schema: {{reasoning, action, params, confidence}}
"""


@app.route("/webhook", methods=["POST"])
@require_api_key
def webhook():
    """
    Endpoint nhận webhook từ AlertManager.
    Xử lý từng alert, gọi Gemini, thực thi tool.
    """
    try:
        payload = request.get_json(force=True, silent=True)
        if not payload:
            logger.error("Received empty or invalid JSON payload")
            return jsonify({"error": "Invalid JSON"}), 400

        alerts = payload.get("alerts", [])
        if not alerts:
            logger.warning("Received webhook with no alerts")
            return jsonify({"warning": "No alerts in payload"}), 200

        logger.info(f"Nhận {len(alerts)} alert(s) từ AlertManager")

        if DEBUG_MODE:
            logger.debug(f"Full payload: {json.dumps(payload, indent=2)}")

    except Exception as e:
        logger.error(f"Error parsing webhook payload: {e}")
        return jsonify({"error": f"Payload parsing failed: {str(e)}"}), 400

    results = []
    for alert in alerts:
        alert_name = alert.get("labels", {}).get("alertname", "Unknown")
        scenario   = alert.get("labels", {}).get("scenario", "unknown")
        status     = alert.get("status", "firing")

        logger.info(f"--- Xử lý: {alert_name} [{scenario}] [{status}] ---")
        webhook_received_at = datetime.now(timezone.utc).isoformat()

        # Bỏ qua alert đã resolve (chỉ log)
        if status == "resolved":
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "alert": alert_name,
                "scenario": scenario,
                "status": "resolved",
                "reasoning": "Alert resolved, no action needed.",
                "action": None,
                "result": None,
                "llm_latency_s": 0,
            }
            action_log.append(entry)
            results.append(entry)
            continue

        # Dry-run nếu không có API key
        if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
            decision = {
                "reasoning": "[DRY-RUN] No API key. Simulating get_top_processes.",
                "action": "get_top_processes",
                "params": {"container_name": "target-app"},
                "confidence": 1.0
            }
            llm_latency = 0.0
        else:
            context = enrich_alert_context(alert)
            prompt = build_prompt(alert, context)
            decision, llm_latency = call_gemini(prompt)

        reasoning  = decision.get("reasoning", "")
        action     = decision.get("action")
        params     = decision.get("params", {})
        confidence = decision.get("confidence", 0.0)

        logger.info(f"AI reasoning: {reasoning}")
        logger.info(f"Action: {action} | Params: {params} | Confidence: {confidence}")

        # Thực thi tool
        tool_result = None
        if action and action in TOOLS:
            logger.info(f"Thực thi tool: {action}({params})")
            t0 = time.time()
            try:
                tool_result = TOOLS[action](**params)
                # Post Grafana annotation marking AI intervention
                annotation_text = f"🤖 {action} — {scenario} | " + " ".join(
                    f"{k}:{v}" for k, v in (context if 'context' in dir() else {}).items()
                )
                post_grafana_annotation(annotation_text, tags=["aiops", "auto-remediation", scenario])
                exec_time = time.time() - t0
                logger.info(f"Tool result ({exec_time:.2f}s): {tool_result[:200]}...")
            except TypeError as e:
                exec_time = time.time() - t0
                tool_result = f"Parameter error: {e}"
                logger.error(f"Tool {action} parameter error: {e}")
            except Exception as e:
                exec_time = time.time() - t0
                tool_result = f"Tool execution error: {e}"
                logger.error(f"Tool {action} execution error: {e}")
        elif action:
            tool_result = f"Unknown tool: {action}"
            logger.warning(tool_result)
        else:
            logger.info("No action required for this alert")
            tool_result = "No action taken"

        # Ghi vào action log
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "webhook_received_at": webhook_received_at,
            "alert": alert_name,
            "scenario": scenario,
            "status": status,
            "reasoning": reasoning,
            "action": action,
            "params": params,
            "confidence": confidence,
            "result": tool_result,
            "llm_latency_s": round(llm_latency, 3),
        }
        action_log.append(entry)
        if len(action_log) > 100:
            action_log.pop(0)

        results.append(entry)

    return jsonify(results), 200


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "gemini_configured": bool(GEMINI_API_KEY),
        "actions_logged": len(action_log),
    })


@app.route("/logs")
@require_api_key
def logs():
    """Trả về 50 action gần nhất — dùng để xem trong video demo."""
    limit = int(request.args.get("limit", 50))
    return jsonify(action_log[-limit:])


@app.route("/logs/ui")
@require_api_key
def logs_ui():
    """Live HTML table of the 50 most recent AI actions — for screen recording."""
    limit = int(request.args.get("limit", 50))
    entries = action_log[-limit:]

    rows = ""
    for e in reversed(entries):
        ts = e.get("timestamp", "")[:19].replace("T", " ")
        recv = e.get("webhook_received_at", "")[:19].replace("T", " ")

        # Compute MTTR if both timestamps are present and parseable
        mttr_cell = "—"
        try:
            if ts and recv:
                t_recv = datetime.fromisoformat(e["webhook_received_at"].replace("Z", "+00:00"))
                t_done = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
                mttr_s = round((t_done - t_recv).total_seconds(), 1)
                mttr_cell = f"{mttr_s}s"
        except Exception:
            pass

        action  = e.get("action") or "—"
        conf    = f"{e.get('confidence', 0):.2f}" if e.get("confidence") is not None else "—"
        llm_lat = f"{e.get('llm_latency_s', 0):.2f}s" if e.get("llm_latency_s") is not None else "—"
        result  = str(e.get("result") or "")[:80]
        alert   = e.get("alert", "")
        scenario = e.get("scenario", "")

        severity_color = {"critical": "#dc3545", "warning": "#fd7e14"}.get(
            e.get("status", ""), "#6c757d"
        )

        rows += f"""
        <tr>
          <td>{ts}</td>
          <td><strong>{alert}</strong></td>
          <td><span style="color:{severity_color}">{scenario}</span></td>
          <td><code>{action}</code></td>
          <td>{conf}</td>
          <td>{llm_lat}</td>
          <td>{mttr_cell}</td>
          <td style="font-size:0.85em">{result}</td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="8" style="text-align:center;padding:2rem">No actions recorded yet.</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="5">
  <title>AIOps Agent — Live Action Log</title>
  <style>
    body {{ font-family: monospace; background:#0d1117; color:#c9d1d9; margin:0; padding:1rem; }}
    h1   {{ color:#58a6ff; margin-bottom:0.5rem; }}
    p    {{ color:#8b949e; margin-top:0; }}
    table  {{ border-collapse:collapse; width:100%; }}
    th,td  {{ border:1px solid #30363d; padding:0.4rem 0.6rem; text-align:left; }}
    th     {{ background:#161b22; color:#58a6ff; }}
    tr:hover {{ background:#161b22; }}
    code   {{ background:#161b22; padding:2px 5px; border-radius:3px; }}
  </style>
</head>
<body>
  <h1>🤖 AIOps Agent — Live Action Log</h1>
  <p>Auto-refreshes every 5 seconds. Showing last {limit} actions (newest first).</p>
  <table>
    <thead>
      <tr>
        <th>Timestamp</th><th>Alert</th><th>Scenario</th><th>Action</th>
        <th>Confidence</th><th>LLM Latency</th><th>MTTR</th><th>Result</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>"""

    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


if __name__ == "__main__":
    logger.info(f"AIOps Agent starting (name={__name__}) on port 8080...")
    # Explicitly using 0.0.0.0 to bind to all interfaces in container
    app.run(host="0.0.0.0", port=8080, threaded=True, debug=False)
