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
import inspect
import re
from datetime import datetime, timezone
import threading
from collections import deque
from flask import Flask, request, jsonify
from google import genai
from google.genai import types as genai_types  # GenerateContentConfig, etc.

from tools import TOOLS, TOOLS_DESCRIPTION, post_grafana_annotation
import requests as _requests  # aliased to avoid collision with tools.requests
from prometheus_client import Gauge

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

# ── MTTR Prometheus gauges ──────────────────────────────────
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

# ── Gemini setup ─────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemma-3-1b-it")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY not set! Agent will run in dry-run mode.")

_genai_client = genai.Client(api_key=GEMINI_API_KEY)

# ── Throttle & Auth ───────────────────────────────────────────
_last_llm_call: float = 0.0
_llm_lock = threading.Lock()
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
action_log = deque(maxlen=100)

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

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(queries), 5) or 1) as executor:
        future_to_key = {executor.submit(_prom_query, query): key for key, query in queries.items()}
        for future in concurrent.futures.as_completed(future_to_key):
            key = future_to_key[future]
            raw = future.result()
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

RESPONSE RULES (MANDATORY - follow exactly):
- Respond with ONLY a JSON object — no text, no markdown code fences, no extra formatting.
- Schema: {{"reasoning": "<analysis>", "action": "<tool_name_only or null>", "params": {{}}, "confidence": <float>}}
- CRITICAL: "action" must be ONLY the tool name (e.g. "restart_service"), NOT the function call itself. DO NOT include parentheses or arguments in the action field.
- Example CORRECT response:
  {{"reasoning": "High CPU detected at 92%", "action": "auto_kill_cpu_stress", "params": {{"container_name": "target-app", "cpu_threshold": 80}}, "confidence": 0.9}}
- Example WRONG response (DO NOT do this):
  {{"reasoning": "...", "action": "auto_kill_cpu_stress(container_name=...)", "params": {{}}, ...}}  ← WRONG
- Use null action only if the metrics clearly show the alert has already self-resolved.
- Base your reasoning on the actual metric VALUES provided — mention the numbers.

SCENARIO → TOOL MAPPING (STRICT — never mix tools across scenarios):

  scenario=cpu_stress   → ONLY use: auto_kill_cpu_stress OR get_top_processes OR kill_process
                          e.g. "action": "auto_kill_cpu_stress", "params": {{"container_name": "target-app", "cpu_threshold": 80}}
                          NEVER use reduce_system_load for cpu_stress.

  scenario=ddos         → ONLY use: restart_service
                          e.g. "action": "restart_service", "params": {{"container_name": "target-app"}}

  scenario=memory_stress → ONLY use: restart_service OR reduce_system_load
                           e.g. "action": "restart_service", "params": {{"container_name": "target-app"}}

  scenario=system_load  → ONLY use: reduce_system_load OR check_system_load
                          e.g. "action": "reduce_system_load", "params": {{}}
                          reduce_system_load() and check_system_load() take NO parameters.

THRESHOLDS (secondary — scenario mapping takes priority):
- cpu_stress:    container_cpu > 70% → auto_kill_cpu_stress
- ddos:          req_rate spike OR latency_ms > 1500 → restart_service
- memory_stress: memory_pct > 75% OR memory_available_mb < 300 → restart_service
- system_load:   load1 > 3.0 → reduce_system_load

CRITICAL: reduce_system_load() and check_system_load() take NO parameters — params must be {{}}.
CRITICAL: "action" field must contain ONLY the tool name, parameters go in "params" field.
"""


def call_gemini(prompt: str, retry_count: int = 0) -> tuple[dict, float]:
    """
    Gọi Gemini API với throttle 3s.
    Trả về (decision_dict, latency_seconds).
    Detects truncation and retries once if needed.
    """
    global _last_llm_call
    MAX_RETRIES = 1

    # Throttle
    with _llm_lock:
        wait = MIN_INTERVAL - (time.time() - _last_llm_call)
        if wait > 0:
            logger.info(f"Throttle: chờ {wait:.1f}s trước khi gọi Gemini...")
            time.sleep(wait)
        _last_llm_call = time.time() + (wait if wait > 0 else 0)

    start = time.time()
    try:
        response = _genai_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=SYSTEM_PROMPT + "\n\n" + prompt,
            config=genai_types.GenerateContentConfig(
                max_output_tokens=512,
                temperature=0.2,
            ),
        )
        latency = time.time() - start
        
        with _llm_lock:
            _last_llm_call = time.time()

        raw = response.text.strip()

        # Log FULL raw response for debugging
        logger.info(f"Gemini full response ({latency:.2f}s, {len(raw)} chars):\n{raw}")

        # Strip markdown code fence if present
        if raw.startswith("```"):
            # Remove ``` and language tag (if any) from start
            raw = re.sub(r'^```\w*\n?', '', raw, flags=re.MULTILINE)
        if raw.endswith("```"):
            # Remove ``` from end
            raw = raw[:-3]

        raw = raw.strip()
        logger.debug(f"After stripping markdown: {raw[:100]}...")

        # Detect truncation: JSON should end with closing brace
        is_truncated = not raw.rstrip().endswith('}')
        if is_truncated and retry_count < MAX_RETRIES:
            logger.warning(f"Response appears truncated (doesn't end with }}), retrying... (attempt {retry_count + 2}/{MAX_RETRIES + 1})")
            return call_gemini(prompt, retry_count=retry_count + 1)

        # Extract JSON from response
        try:
            # Try direct parsing first
            decision = json.loads(raw)
        except json.JSONDecodeError as e:
            # Try to find JSON block in text (handles edge cases)
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                json_text = json_match.group()
                logger.debug(f"Extracted JSON block: {json_text[:100]}...")
                decision = json.loads(json_text)
            else:
                raise json.JSONDecodeError("No valid JSON found in response", raw, 0)

        return decision, latency

    except json.JSONDecodeError as e:
        latency = time.time() - start
        logger.error(f"JSON parse error: {e}")
        logger.error(f"Raw response (full): {response.text}")  # Log full response on error
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
                "webhook_received_at": webhook_received_at,
                "alert": alert_name,
                "scenario": scenario,
                "status": "resolved",
                "reasoning": "Alert resolved, no action needed.",
                "action": None,
                "params": {},
                "context": {},
                "result": None,
                "llm_latency_s": 0,
            }
            action_log.append(entry)
            results.append(entry)
            continue

        # Dry-run nếu không có API key
        if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
            context = {}
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

        # Ensure params is always a dict before unpacking — LLM may return a string, list, or None
        if not isinstance(params, dict):
            logger.warning(f"params from LLM was {type(params).__name__} (value: {params!r}), resetting to {{}}")
            params = {}

        # Sanitize params: keep only keys the target function actually accepts.
        # This prevents TypeError when the LLM hallucinates extra/wrong param names.
        if action and action in TOOLS:
            target_fn = TOOLS[action]
            sig = inspect.signature(target_fn)
            accepted = set(sig.parameters.keys())
            has_var_keyword = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
            if not has_var_keyword:
                dropped = {k: v for k, v in params.items() if k not in accepted}
                if dropped:
                    logger.warning(f"Dropping unsupported params for {action}: {dropped}")
                params = {k: v for k, v in params.items() if k in accepted}

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
                    f"{k}:{v}" for k, v in context.items()
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

        # ── Record MTTR metrics ──────────────────────────────────
        action_taken_at = datetime.now(timezone.utc)
        # Response latency: action_taken_at − webhook_received_at
        try:
            t_recv = datetime.fromisoformat(webhook_received_at)
            response_latency = (action_taken_at - t_recv).total_seconds()
            AGENT_RESPONSE_LATENCY.labels(agent_type="ai").set(response_latency)
        except Exception:
            response_latency = None

        # MTTR: action_taken_at − alert startsAt
        try:
            starts_at_raw = alert.get("startsAt", "")
            if starts_at_raw:
                t_start = datetime.fromisoformat(starts_at_raw.replace("Z", "+00:00"))
                mttr = (action_taken_at - t_start).total_seconds()
                AGENT_MTTR.labels(agent_type="ai").set(mttr)
            else:
                mttr = None
        except Exception:
            mttr = None

        # Ghi vào action log
        entry = {
            "timestamp": action_taken_at.isoformat(),
            "webhook_received_at": webhook_received_at,
            "alert": alert_name,
            "scenario": scenario,
            "status": status,
            "context": context,
            "reasoning": reasoning,
            "action": action,
            "params": params,
            "confidence": confidence,
            "result": tool_result,
            "llm_latency_s": round(llm_latency, 3),
            "response_latency_s": round(response_latency, 3) if response_latency is not None else None,
            "mttr_s": round(mttr, 3) if mttr is not None else None,
        }
        action_log.append(entry)

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
    try:
        limit = min(int(request.args.get("limit", 50)), 100)
    except (ValueError, TypeError):
        limit = 50
    return jsonify(list(action_log)[-limit:])


@app.route("/logs/ui")
@require_api_key
def logs_ui():
    """Live HTML table of the 50 most recent AI actions — for screen recording."""
    try:
        limit = min(int(request.args.get("limit", 50)), 100)
    except (ValueError, TypeError):
        limit = 50
    entries = list(action_log)[-limit:]

    rows = ""
    for e in reversed(entries):
        raw_ts  = e.get("timestamp", "")
        raw_recv = e.get("webhook_received_at", "")
        ts_display = raw_ts[11:19] if len(raw_ts) >= 19 else raw_ts  # HH:MM:SS only

        # ── MTTR ─────────────────────────────────────────────────
        mttr_s = None
        try:
            if raw_ts and raw_recv:
                t_recv = datetime.fromisoformat(raw_recv.replace("Z", "+00:00"))
                t_done = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                mttr_s = round((t_done - t_recv).total_seconds(), 1)
        except Exception:
            pass

        if mttr_s is None:
            mttr_cell = '<span style="color:#6c757d">—</span>'
        elif mttr_s < 10:
            mttr_cell = f'<span style="color:#3fb950;font-weight:bold">{mttr_s}s</span>'
        elif mttr_s < 30:
            mttr_cell = f'<span style="color:#d29922">{mttr_s}s</span>'
        else:
            mttr_cell = f'<span style="color:#f85149">{mttr_s}s</span>'

        # ── Core fields ───────────────────────────────────────────
        alert_name = e.get("alert", "Unknown")
        scenario   = e.get("scenario", "")
        status     = e.get("status", "firing")
        action     = e.get("action")
        params     = e.get("params") or {}
        confidence = e.get("confidence")
        llm_lat_s  = e.get("llm_latency_s", 0)
        reasoning  = e.get("reasoning", "")
        result_raw = str(e.get("result") or "")
        ctx        = e.get("context") or {}

        # ── Row category ─────────────────────────────────────────
        # resolved   → dim row
        # action taken → normal
        # no action (LLM said null) → soft orange tint
        # throttled (LLM latency == 0 and firing) → soft purple tint
        is_resolved   = (status == "resolved")
        is_throttled  = (status == "firing" and llm_lat_s == 0 and not action)
        is_no_action  = (status == "firing" and llm_lat_s > 0 and not action)
        is_error      = action and ("ERROR" in result_raw or "error" in result_raw.lower())

        if is_resolved:
            row_style = "opacity:0.45"
        elif is_throttled:
            row_style = "background:rgba(130,80,255,0.07)"
        elif is_no_action:
            row_style = "background:rgba(210,153,34,0.07)"
        elif is_error:
            row_style = "background:rgba(248,81,73,0.07)"
        else:
            row_style = "background:rgba(63,185,80,0.05)"

        # ── Alert + Scenario cell ─────────────────────────────────
        scenario_colors = {
            "cpu_stress":    "#e3b341",
            "ddos":          "#f85149",
            "memory_stress": "#d2a8ff",
            "system_load":   "#79c0ff",
            "overhead":      "#6e7681",
        }
        sc_color = scenario_colors.get(scenario, "#8b949e")
        status_badge_color = "#3fb950" if is_resolved else "#f85149"
        status_label       = "RESOLVED" if is_resolved else "FIRING"

        alert_cell = (
            f'<strong style="color:#e6edf3">{alert_name}</strong><br>'
            f'<span style="color:{sc_color};font-size:0.78em">&#9632; {scenario}</span>'
            f'&nbsp;<span style="color:{status_badge_color};font-size:0.72em;border:1px solid {status_badge_color};'
            f'padding:1px 4px;border-radius:3px">{status_label}</span>'
        )

        # ── Live Metrics cell ────────────────────────────────────
        if ctx:
            metric_lines = "".join(
                f'<div><span style="color:#8b949e">{k}:</span> '
                f'<span style="color:#e6edf3">{v}</span></div>'
                for k, v in ctx.items()
            )
            metrics_cell = f'<div style="font-size:0.80em;line-height:1.6">{metric_lines}</div>'
        elif is_resolved:
            metrics_cell = '<span style="color:#6c757d;font-size:0.80em">alert resolved</span>'
        elif is_throttled:
            metrics_cell = '<span style="color:#8957e5;font-size:0.80em">⏸ throttled / no LLM call</span>'
        else:
            metrics_cell = '<span style="color:#6c757d;font-size:0.80em">—</span>'

        # ── Decision cell (action + params + reasoning) ───────────
        if is_resolved:
            decision_cell = '<span style="color:#3fb950;font-size:0.85em">✔ self-resolved</span>'
        elif is_throttled:
            decision_cell = '<span style="color:#8957e5;font-size:0.85em">⏸ skipped (throttle / dup)</span>'
        elif not action:
            short_reason  = reasoning[:120] + ("…" if len(reasoning) > 120 else "")
            decision_cell = (
                f'<span style="color:#d29922;font-size:0.85em">— no action</span><br>'
                f'<span style="color:#6c757d;font-size:0.78em" title="{reasoning}">{short_reason}</span>'
            )
        else:
            params_str = (
                "(" + ", ".join(f'{k}=<em>{v}</em>' for k, v in params.items()) + ")"
                if params else "()"
            )
            short_reason = reasoning[:130] + ("…" if len(reasoning) > 130 else "")
            decision_cell = (
                f'<code style="color:#79c0ff">{action}</code>'
                f'<span style="color:#6e7681;font-size:0.80em">{params_str}</span><br>'
                f'<span style="color:#8b949e;font-size:0.78em" title="{reasoning}">💬 {short_reason}</span>'
            )

        # ── Confidence + LLM latency cell ─────────────────────────
        if confidence is not None and llm_lat_s > 0:
            if confidence >= 0.8:
                conf_color = "#3fb950"
            elif confidence >= 0.5:
                conf_color = "#d29922"
            else:
                conf_color = "#f85149"
            conf_cell = (
                f'<span style="color:{conf_color};font-weight:bold">{confidence:.2f}</span><br>'
                f'<span style="color:#6c757d;font-size:0.78em">LLM {llm_lat_s:.2f}s</span>'
            )
        else:
            conf_cell = '<span style="color:#6c757d">—</span>'

        # ── Result cell ───────────────────────────────────────────
        result_display = result_raw[:250] + ("…" if len(result_raw) > 250 else "")
        if not result_raw or is_resolved:
            result_cell = '<span style="color:#6c757d;font-size:0.80em">—</span>'
        elif "ERROR" in result_raw or "error" in result_raw.lower():
            result_cell = f'<span style="color:#f85149;font-size:0.80em" title="{result_raw}">⚠ {result_display}</span>'
        elif "✅" in result_raw or "Restarted" in result_raw or "Killed" in result_raw or "limit" in result_raw.lower():
            result_cell = f'<span style="color:#3fb950;font-size:0.80em" title="{result_raw}">✔ {result_display}</span>'
        else:
            result_cell = f'<span style="color:#c9d1d9;font-size:0.80em" title="{result_raw}">{result_display}</span>'

        rows += f"""
        <tr style="{row_style}">
          <td style="white-space:nowrap;color:#8b949e;font-size:0.85em">{ts_display}</td>
          <td>{alert_cell}</td>
          <td>{metrics_cell}</td>
          <td>{decision_cell}</td>
          <td style="text-align:center">{conf_cell}</td>
          <td style="text-align:center">{mttr_cell}</td>
          <td>{result_cell}</td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:#6c757d">No actions recorded yet.</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="5">
  <title>AIOps Agent — Live Action Log</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body  {{ font-family: ui-monospace, "Cascadia Code", "Fira Code", monospace;
             background:#0d1117; color:#c9d1d9; margin:0; padding:1rem 1.5rem; }}
    h1    {{ color:#58a6ff; margin-bottom:0.25rem; font-size:1.3rem; }}
    .sub  {{ color:#8b949e; margin-top:0; font-size:0.85rem; margin-bottom:1rem; }}
    table {{ border-collapse:collapse; width:100%; table-layout:auto; }}
    th,td {{ border:1px solid #21262d; padding:0.45rem 0.65rem; vertical-align:top; }}
    th    {{ background:#161b22; color:#58a6ff; font-size:0.82rem;
             text-transform:uppercase; letter-spacing:0.05em; white-space:nowrap; }}
    tr:hover td {{ background:#161b22 !important; }}
    code  {{ background:#161b22; padding:2px 5px; border-radius:3px; font-size:0.88em; }}
    .legend {{ display:flex; gap:1.5rem; margin-bottom:0.75rem; font-size:0.78rem; color:#6c757d; }}
    .legend span {{ display:flex; align-items:center; gap:0.3rem; }}
    .dot  {{ width:9px; height:9px; border-radius:50%; display:inline-block; }}
  </style>
</head>
<body>
  <h1>🤖 AIOps Agent — Live Action Log</h1>
  <p class="sub">Auto-refreshes every 5 seconds &nbsp;·&nbsp; Showing last {limit} actions (newest first)</p>
  <div class="legend">
    <span><span class="dot" style="background:#3fb950"></span> Action taken</span>
    <span><span class="dot" style="background:#d29922"></span> No action (metrics OK)</span>
    <span><span class="dot" style="background:#8957e5"></span> Throttled / skipped</span>
    <span><span class="dot" style="background:#f85149"></span> Error</span>
    <span><span class="dot" style="background:#6c757d"></span> Resolved</span>
  </div>
  <table>
    <thead>
      <tr>
        <th>Time</th>
        <th>Alert / Status</th>
        <th>Live Metrics at Decision</th>
        <th>AI Decision + Reasoning</th>
        <th>Conf / LLM</th>
        <th>MTTR</th>
        <th>Result</th>
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
