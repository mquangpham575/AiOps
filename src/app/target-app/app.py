"""
Target App - Flask application dùng để tạo sự cố trong thực nghiệm.
Endpoints:
  GET /           → trang chủ (load test target)
  GET /heavy      → endpoint nặng, sleep ngẫu nhiên (test latency)
  GET /cpu        → tính toán nặng (test CPU stress)
  GET /health     → health check
  GET /metrics    → Prometheus metrics (tự động qua prometheus_flask_exporter)
"""

import os, time, math, random
from flask import Flask, jsonify, Response, request

app = Flask(__name__)
try:
    from prometheus_flask_exporter import PrometheusMetrics
    PrometheusMetrics(app, group_by="endpoint")
except Exception as e:
    print(f"Warning: PrometheusMetrics init failed: {e}")
    # Fallback: Simple /metrics endpoint if exporter fails
    @app.route("/metrics")
    def metrics():
        return Response("# No metrics available\n", mimetype="text/plain")


@app.route("/")
def index():
    return jsonify({
        "status": "ok",
        "message": "Target app is running",
        "timestamp": time.time()
    })


@app.route("/heavy")
def heavy():
    """Giả lập endpoint chậm: sleep 0.1–0.5s → dễ trigger HighRequestLatency."""
    delay = random.uniform(0.1, 0.5)
    time.sleep(delay)
    return jsonify({
        "status": "ok",
        "delay_ms": round(delay * 1000, 2)
    })


@app.route("/cpu")
def cpu_burn():
    """Tính toán nặng ~0.3s → dùng trong kịch bản stress-ng kết hợp."""
    start = time.time()
    result = sum(math.sqrt(i) for i in range(500_000))
    elapsed = time.time() - start
    return jsonify({
        "status": "ok",
        "elapsed_ms": round(elapsed * 1000, 2),
        "result": round(result, 2)
    })


@app.route("/memory")
def memory_stress():
    """Allocate memory and hold it — triggers HighMemoryUsage alert under concurrent load.

    Query params:
        mb (int): megabytes to allocate, default 20, max capped at 100.

    Example:
        GET /memory?mb=50
        {"status": "ok", "allocated_mb": 50, "held_s": 10}
    """
    try:
        mb = int(request.args.get("mb", 20))
    except (ValueError, TypeError):
        return jsonify({"error": "mb must be an integer"}), 400

    mb = max(1, min(mb, 100))  # clamp: 1MB minimum, 100MB maximum

    # Allocate memory
    _buffer = bytearray(mb * 1024 * 1024)

    # Hold it for 10 seconds to sustain pressure under concurrent Locust load
    try:
        hold_s = int(os.environ.get("MEMORY_HOLD_SECONDS", "10"))
    except (ValueError, TypeError):
        hold_s = 10
    time.sleep(hold_s)

    # Release and force immediate GC so Prometheus sees a clean memory drop
    del _buffer
    import gc; gc.collect()

    return jsonify({
        "status": "ok",
        "allocated_mb": mb,
        "held_s": hold_s,
    })


@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
