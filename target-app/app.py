"""
Target App - Flask application dùng để tạo sự cố trong thực nghiệm.
Endpoints:
  GET /           → trang chủ (load test target)
  GET /heavy      → endpoint nặng, sleep ngẫu nhiên (test latency)
  GET /cpu        → tính toán nặng (test CPU stress)
  GET /health     → health check
  GET /metrics    → Prometheus metrics (tự động qua prometheus_flask_exporter)
"""

import time, math, random
from flask import Flask, jsonify, Response

app = Flask(__name__)
try:
    from prometheus_flask_exporter import PrometheusFlaskExporter
    PrometheusFlaskExporter(app, group_by="endpoint")
except Exception as e:
    print(f"Warning: PrometheusFlaskExporter init failed: {e}")
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


@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
