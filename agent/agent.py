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

import os, json, time, logging
from datetime import datetime, timezone
from flask import Flask, request, jsonify
import google.generativeai as genai

from tools import TOOLS, TOOLS_DESCRIPTION

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
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY not set! Agent will run in dry-run mode.")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)

# ── Throttle: configurable interval between Gemini calls ───────────
_last_llm_call: float = 0.0
MIN_INTERVAL: float = float(os.environ.get("AI_THROTTLE_INTERVAL", "3.0"))

# ── Action log: lưu 100 action gần nhất ─────────────────────
action_log: list[dict] = []

# ── System prompt cho AI Agent ───────────────────────────────
SYSTEM_PROMPT = f"""Bạn là một AI Agent chuyên vận hành hệ thống mạng (AIOps).
Nhiệm vụ: khi nhận cảnh báo, phân tích và quyết định hành động khắc phục TỰ ĐỘNG.

{TOOLS_DESCRIPTION}

QUY TẮC PHẢN HỒI (BẮT BUỘC):
- Chỉ trả về JSON, không có text ngoài JSON.
- Format chính xác:
{{
  "reasoning": "Giải thích ngắn gọn tại sao chọn hành động này (1-2 câu)",
  "action": "tên_tool hoặc null nếu không cần hành động",
  "params": {{"tham_số": "giá_trị"}},
  "confidence": 0.0-1.0
}}

VÍ DỤ:
Cảnh báo CPU 95%:
{{"reasoning": "CPU quá tải do stress-ng, cần xem process và kill.", "action": "get_top_processes", "params": {{"container_name": "target-app"}}, "confidence": 0.9}}

Cảnh báo latency cao:
{{"reasoning": "Latency cao do flood request, áp dụng rate limit ngay.", "action": "apply_rate_limit", "params": {{"interface": "eth0", "rate": "50/sec"}}, "confidence": 0.85}}
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


def build_prompt(alert: dict) -> str:
    """Xây dựng prompt từ alert payload của AlertManager."""
    alert_name  = alert.get("labels", {}).get("alertname", "Unknown")
    severity    = alert.get("labels", {}).get("severity", "unknown")
    scenario    = alert.get("labels", {}).get("scenario", "unknown")
    summary     = alert.get("annotations", {}).get("summary", "")
    description = alert.get("annotations", {}).get("description", "")
    starts_at   = alert.get("startsAt", "")
    status      = alert.get("status", "firing")

    return f"""=== CẢNH BÁO HỆ THỐNG ===
Tên cảnh báo : {alert_name}
Mức độ       : {severity}
Kịch bản     : {scenario}
Trạng thái   : {status}
Bắt đầu lúc  : {starts_at}
Tóm tắt      : {summary}
Chi tiết      : {description}

Hãy phân tích và quyết định hành động khắc phục phù hợp.
"""


@app.route("/webhook", methods=["POST"])
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
            prompt = build_prompt(alert)
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
def logs():
    """Trả về 50 action gần nhất — dùng để xem trong video demo."""
    limit = int(request.args.get("limit", 50))
    return jsonify(action_log[-limit:])


if __name__ == "__main__":
    logger.info("AIOps Agent starting on port 8080...")
    app.run(host="0.0.0.0", port=8080, threaded=True)
