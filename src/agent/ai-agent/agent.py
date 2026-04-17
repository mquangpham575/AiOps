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
from prometheus_client import Gauge, Counter

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
    from prometheus_flask_exporter import PrometheusMetrics
    PrometheusMetrics(app)
    logger.info("Prometheus metrics enabled")
except Exception as e:
    logger.warning(f"Prometheus exporter skipped: {e}")
    # Fallback: tạo /metrics endpoint đơn giản
    from flask import Response
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    @app.route("/metrics")
    def metrics():
        # Expose internal agent metrics for Prometheus scraping (fallback mode).
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

# ── MTTR Prometheus gauges ──────────────────────────────────
# AGENT_RESPONSE_LATENCY: Thời gian suy luận của AI (từ khi nhận webhook đến khi ra quyết định)
AGENT_RESPONSE_LATENCY = Gauge(
    "agent_response_latency_seconds",
    "Time from webhook received to action taken (AI reasoning time)",
    ["agent_type"],
)
# AGENT_MTTR: Thời gian từ khi Alert bắt đầu đến khi hồi phục (Scientific MTTR)
# Chúng tôi map labels(agent_type='ai') vào đây để dashboard hiển thị giá trị tốt nhất.
AGENT_MTTR = Gauge(
    "agent_mttr_seconds",
    "End-to-end incident response time (alert startsAt to recovery detected)",
    ["agent_type"],
)
# AGENT_MTTA: Mean Time To Action (Legacy MTTR - alert startsAt đến khi thực thi tool)
AGENT_MTTA = Gauge(
    "agent_mtta_seconds",
    "Time from alert startsAt to first remediation action taken",
    ["agent_type"],
)

# AGENT_REMEDIATION_COUNT: Theo dõi số lượng hành động remediation (success/failure/resolved)
AGENT_REMEDIATION_COUNT = Counter(
    "agent_remediation_count_total",
    "Total count of remediation actions taken by the agent",
    ["agent_type", "status"],
)

# AGENT_CONFIDENCE: Độ tự tin của AI trong quyết định gần nhất
AGENT_CONFIDENCE = Gauge(
    "agent_confidence_score",
    "Latest AI confidence score for decision making",
    ["agent_type"],
)

# Khởi tạo giá trị 0 cho các labels thông dụng để Prometheus scrape được ngay từ đầu
# Tránh tình trạng "No Data" trên dashboard.
AGENT_RESPONSE_LATENCY.labels(agent_type="ai").set(0)
AGENT_MTTR.labels(agent_type="ai").set(0)
AGENT_MTTA.labels(agent_type="ai").set(0)
AGENT_CONFIDENCE.labels(agent_type="ai").set(0)
AGENT_REMEDIATION_COUNT.labels(agent_type="ai", status="success").inc(0)
AGENT_REMEDIATION_COUNT.labels(agent_type="ai", status="failure").inc(0)
AGENT_REMEDIATION_COUNT.labels(agent_type="ai", status="resolved").inc(0)
AGENT_REMEDIATION_COUNT.labels(agent_type="ai", status="monitoring").inc(0)

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
    # Decorator to enforce API key authentication for protected endpoints.
    """Decorator to require X-Agent-Key header for access."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        # Independently collect all possible keys
        header_key = request.headers.get("X-Agent-Key")
        
        auth_header = request.headers.get("Authorization", "")
        bearer_key = auth_header.split(" ")[-1] if auth_header.startswith("Bearer ") else None
        
        query_key = request.args.get("api_key")

        # Check if ANY source contains a valid key
        is_authorized = False
        for provided in [header_key, bearer_key, query_key]:
            if provided and hmac.compare_digest(provided, AGENT_API_KEY):
                is_authorized = True
                break
        
        if not is_authorized:
            logger.warning(f"Unauthorized access attempt from {repr(request.remote_addr)} | Header: {bool(header_key)} | Bearer: {bool(bearer_key)} | Query: {bool(query_key)}")
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
    "HighRequestRate":    "ddos",
    "HighRequestLatency": "ddos",
    "HighMemoryUsage":    "memory_stress",
    "HighSystemLoad":     "system_load",
    "CriticalSystemLoad": "system_load",
}

# ── Recovery Thresholds (used for scientific MTTR) ───────────
_RECOVERY_THRESHOLDS = {
    "cpu_stress":    {"container_cpu": 30.0},  # Wait until CPU < 30%
    "ddos":          {"latency_ms": 300.0},    # Wait until latency < 300ms
    "memory_stress": {"memory_pct": 60.0},     # Wait until memory < 60%
    "system_load":   {"load1": 1.5},           # Wait until load < 1.5
}


def _prom_query(query: str) -> float | str:
    # Execute an instant query against the Prometheus API and return the numeric result.
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
    # Fetch real-time system metrics from Prometheus to provide context for the AI agent.
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

    # Query in a deterministic order (dict insertion order) to keep logs stable
    # and to make unit tests reliable under mocked responses.
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
    # Interface with the Gemini API to obtain a structured remediation decision.
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
    # Construct a detailed instructional prompt for the LLM based on alert data and live metrics.
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
Respond ONLY with valid JSON matching the schema: {{reasoning, action, params, confidence}}.
Note: 'confidence' must be a number between 0 and 100 representing your percentage of certainty.
"""


def _poll_recovery(log_id: str, scenario: str, start_time: datetime):
    # Background thread to poll Prometheus until system recovery is detected for accurate MTTR.
    """
    Polls Prometheus every 5s for up to 5 minutes.
    When recovery thresholds are met, updates the action log entry and Prometheus gauges.
    """
    timeout_s = 300
    poll_interval = 5
    elapsed = 0
    
    thresholds = _RECOVERY_THRESHOLDS.get(scenario, {})
    if not thresholds:
        return

    logger.info(f"[metrics] MTTR tracking started for {log_id} ({scenario})")

    while elapsed < timeout_s:
        time.sleep(poll_interval)
        elapsed += poll_interval
        
        # Build context (query live metrics)
        try:
            # We mock an alert dict for enrich_alert_context
            ctx = enrich_alert_context({"labels": {"scenario": scenario}})
            
            is_recovered = True
            for metric, threshold in thresholds.items():
                val = ctx.get(metric)
                
                # Handle missing keys or "N/A" values from Prometheus
                if val is None or val == "N/A":
                    # If we can't get the metric, we can't confirm recovery
                    is_recovered = False
                    break
                
                # Check threshold (only if val is numeric)
                if float(val) > threshold:
                    is_recovered = False
                    break
            
            if is_recovered:
                recovery_time = datetime.now(timezone.utc)
                mttr_s = round((recovery_time - start_time).total_seconds(), 1)
                
                # Update action log entry
                for entry in action_log:
                    if entry.get("id") == log_id:
                        entry["mttr_actual_s"] = mttr_s
                        entry["recovered_at"] = recovery_time.isoformat()
                        break
                
                # Update Prometheus Metric
                # Update Prometheus Metric with high priority 'ai' label for dashboard headline
                AGENT_MTTR.labels(agent_type="ai").set(mttr_s)
                logger.info(f"[metrics] RECOVERY DETECTED for {log_id}. MTTR: {mttr_s}s")
                return

        except Exception as e:
            logger.warning(f"[metrics] Error in recovery polling: {e}")

    logger.warning(f"[metrics] MTTR tracking timed out for {log_id} after {timeout_s}s")


@app.route("/webhook", methods=["POST"])
@require_api_key
def webhook():
    # Handle incoming alert webhooks from AlertManager and orchestrate the remediation workflow.
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
        log_id = f"{int(time.time())}-{alert_name[:10]}"

        # Bỏ qua alert đã resolve (chỉ log)
        if status == "resolved":
            entry = {
                "id": log_id,
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
            AGENT_REMEDIATION_COUNT.labels(agent_type="ai", status="resolved").inc()
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

        AGENT_CONFIDENCE.labels(agent_type="ai").set(confidence)
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
                AGENT_REMEDIATION_COUNT.labels(agent_type="ai", status="success").inc()
                logger.info(f"Tool result ({exec_time:.2f}s): {tool_result[:200]}...")
            except TypeError as e:
                exec_time = time.time() - t0
                tool_result = f"Parameter error: {e}"
                AGENT_REMEDIATION_COUNT.labels(agent_type="ai", status="failure").inc()
                logger.error(f"Tool {action} parameter error: {e}")
            except Exception as e:
                exec_time = time.time() - t0
                tool_result = f"Tool execution error: {e}"
                AGENT_REMEDIATION_COUNT.labels(agent_type="ai", status="failure").inc()
                logger.error(f"Tool {action} execution error: {e}")
        elif action:
            tool_result = f"Unknown tool: {action}"
            logger.warning(tool_result)
        else:
            logger.info("No action required for this alert")
            AGENT_REMEDIATION_COUNT.labels(agent_type="ai", status="monitoring").inc()
            tool_result = "No action taken"

        # ── Start Scientific MTTR tracking ──────────────────────
        if action and action in TOOLS:
            try:
                starts_at_raw = alert.get("startsAt", "")
                if starts_at_raw:
                    t_start = datetime.fromisoformat(starts_at_raw.replace("Z", "+00:00"))
                    threading.Thread(
                        target=_poll_recovery,
                        args=(log_id, scenario, t_start),
                        daemon=True
                    ).start()
            except Exception as e:
                logger.error(f"[metrics] Failed to span MTTR thread: {e}")

        # ── Record immediate response metrics ─────────────────────
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
                # AGENT_MTTA: alert startsAt to action taken (baseline/legacy MTTR)
                AGENT_MTTA.labels(agent_type="ai").set(mttr)
            else:
                mttr = None
        except Exception:
            mttr = None

        # Ghi vào action log
        entry = {
            "id": log_id,
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
            "mttr_s": round(mttr, 3) if mttr is not None else None,  # Legacy MTTR
            "mttr_actual_s": None,  # To be filled by background thread
        }
        action_log.append(entry)

        results.append(entry)

    return jsonify(results), 200


@app.route("/health")
def health():
    # Provide a simple health status check for the AI agent service.
    return jsonify({
        "status": "ok",
        "gemini_configured": bool(GEMINI_API_KEY),
        "actions_logged": len(action_log),
    })


@app.route("/logs")
@require_api_key
def logs():
    # Retrieve the recent history of AI actions in JSON format.
    """Trả về 50 action gần nhất — dùng để xem trong video demo."""
    try:
        limit = min(int(request.args.get("limit", 50)), 100)
    except (ValueError, TypeError):
        limit = 50
    return jsonify(list(action_log)[-limit:])


@app.route("/logs/ui")
def logs_ui():
    # Render an interactive HTML dashboard for live monitoring of AI reasoning and actions.
    """Live HTML table of the 50 most recent AI actions — for screen recording."""
    try:
        limit = min(int(request.args.get("limit", 50)), 100)
    except (ValueError, TypeError):
        limit = 50
    entries = list(action_log)[-limit:]

    rows = ""
    for e in reversed(entries):
        raw_ts  = e.get("timestamp", "")
        ts_display = raw_ts[11:19] if len(raw_ts) >= 19 else raw_ts

        # ── MTTR logic ──────────────────────────────────────────
        mttr_legacy = e.get("mttr_s")
        mttr_actual = e.get("mttr_actual_s")
        
        if mttr_actual:
            mttr_cell = f'<div style="color:#3fb950;font-weight:bold" title="Recovery detected">{mttr_actual}s</div><div style="font-size:0.7em;color:#6e7681">recovery</div>'
        elif mttr_legacy:
            mttr_cell = f'<div style="color:#d29922" title="Action time">{mttr_legacy}s</div><div style="font-size:0.7em;color:#6e7681">to action</div>'
        else:
            mttr_cell = '<span style="color:#21262d">—</span>'

        # ── Core fields ──────────────────────────────────────────
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

        is_resolved   = (status == "resolved")
        is_error      = action and ("ERROR" in result_raw or "error" in result_raw.lower())
        
        row_class = "resolved" if is_resolved else ("error" if is_error else ("no-action" if not action else "active"))

        # ── Formatting ───────────────────────────────────────────
        scenario_colors = {"cpu_stress": "#e3b341", "ddos": "#f85149", "memory_stress": "#d2a8ff", "system_load": "#79c0ff"}
        sc_color = scenario_colors.get(scenario, "#8b949e")

        metric_html = "".join(f'<span>{k}:<b>{v}</b></span>' for k, v in ctx.items())
        
        decision_html = ""
        if is_resolved:
            decision_html = '<span class="badge success">ALREADY RESOLVED</span>'
        elif not action:
            decision_html = f'<span class="badge warning">MONITORING</span><p>{reasoning[:120]}...</p>'
        else:
            params_str = ", ".join(f"{k}={v}" for k, v in params.items())
            decision_html = f'<code>{action}({params_str})</code><p>{reasoning[:130]}...</p>'

        conf_pct = int((confidence or 0) * 100)
        conf_color = "#3fb950" if conf_pct > 80 else ("#d29922" if conf_pct > 50 else "#f85149")

        rows += f"""
        <tr class="{row_class}">
          <td class="time">{ts_display}</td>
          <td class="alert">
            <strong>{alert_name}</strong>
            <span style="color:{sc_color}">● {scenario}</span>
          </td>
          <td class="metrics">{metric_html}</td>
          <td class="decision">{decision_html}</td>
          <td class="stat">
            <div class="conf-ring" style="--pct:{conf_pct}; --color:{conf_color}">{conf_pct}%</div>
            <small>LLM {llm_lat_s}s</small>
          </td>
          <td class="stat">{mttr_cell}</td>
          <td class="result">{result_raw[:200]}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="5">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <title>AIOps Center</title>
  <style>
    :root {{
      --bg: #0a0c10; --card: rgba(22, 27, 34, 0.7); --border: #30363d;
      --accent: #58a6ff; --text: #c9d1d9; --text-dim: #8b949e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: 'Outfit', sans-serif; background: var(--bg); color: var(--text);
      margin: 0; padding: 2rem; background-image: radial-gradient(circle at 50% 0%, #161b22 0%, #0a0c10 100%);
      min-height: 100vh;
    }}
    .container {{ max-width: 1400px; margin: 0 auto; }}
    header {{ display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 2rem; }}
    h1 {{ margin: 0; font-weight: 600; font-size: 2rem; letter-spacing: -0.02em; color: var(--accent); }}
    .status-bar {{ display: flex; gap: 1.5rem; font-size: 0.9rem; color: var(--text-dim); }}
    
    table {{ 
        width: 100%; border-collapse: separate; border-spacing: 0 0.5rem; 
        backdrop-filter: blur(12px);
    }}
    th {{ padding: 1rem; text-align: left; color: var(--text-dim); font-weight: 400; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.1em; }}
    tr {{ transition: transform 0.2s; }}
    td {{ 
        padding: 1.2rem 1rem; background: var(--card); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border);
        vertical-align: top;
    }}
    td:first-child {{ border-left: 1px solid var(--border); border-radius: 8px 0 0 8px; }}
    td:last-child {{ border-right: 1px solid var(--border); border-radius: 0 8px 8px 0; }}
    
    .time {{ color: var(--text-dim); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; }}
    .alert strong {{ display: block; margin-bottom: 0.3rem; font-size: 1.1rem; }}
    .alert span {{ font-size: 0.8rem; font-weight: 600; }}
    
    .metrics {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.4rem; min-width: 180px; }}
    .metrics span {{ font-size: 0.75rem; color: var(--text-dim); display: flex; justify-content: space-between; padding-right: 0.5rem; }}
    .metrics b {{ color: var(--text); }}
    
    .decision p {{ margin: 0.5rem 0 0; font-size: 0.85rem; color: var(--text-dim); line-height: 1.4; }}
    .decision code {{ background: rgba(88, 166, 255, 0.1); color: var(--accent); padding: 0.2rem 0.5rem; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; }}
    
    .badge {{ font-size: 0.7rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; display: inline-block; }}
    .badge.success {{ background: rgba(63, 185, 80, 0.2); color: #3fb950; }}
    .badge.warning {{ background: rgba(210, 153, 34, 0.2); color: #d29922; }}
    
    .stat {{ text-align: center; min-width: 80px; }}
    .stat small {{ display: block; color: var(--text-dim); font-size: 0.7rem; margin-top: 0.4rem; }}
    
    .conf-ring {{
        width: 42px; height: 42px; border-radius: 50%; margin: 0 auto;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.75rem; font-weight: 600;
        background: conic-gradient(var(--color) calc(var(--pct) * 1%), #21262d 0);
        position: relative;
    }}
    .conf-ring::after {{ content: ''; position: absolute; inset: 4px; background: var(--bg); border-radius: 50%; z-index: 1; }}
    .conf-ring span {{ position: relative; z-index: 2; }}

    .result {{ font-size: 0.8rem; color: var(--text-dim); max-width: 250px; overflow: hidden; text-overflow: ellipsis; }}
    
    tr.resolved {{ opacity: 0.5; filter: grayscale(0.5); }}
    tr.active td {{ border-color: rgba(88, 166, 255, 0.3); }}
    tr:hover {{ transform: scale(1.005); }}
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
