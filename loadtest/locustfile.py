"""
locustfile.py — Kịch bản 2: DDoS / High Traffic Simulation.

Cách chạy (từ thư mục loadtest/):
  # UI mode (mở http://localhost:8089):
  locust -f locustfile.py --host=http://localhost:5000

  # Headless mode (tự động):
  locust -f locustfile.py --host=http://localhost:5000 \
         --users 500 --spawn-rate 50 --run-time 3m --headless

Metrics cần đo trong Grafana trong lúc chạy:
  - flask_http_request_duration_seconds (latency)
  - flask_http_requests_total (throughput)
  - node_network_receive_bytes_total (bandwidth)
"""

from locust import HttpUser, task, between, events
import time


class NormalUser(HttpUser):
    """User thông thường — weight cao hơn."""
    weight = 1
    wait_time = between(0.5, 1.5)

    @task(3)
    def index(self):
        self.client.get("/", name="GET /")

    @task(1)
    def heavy(self):
        self.client.get("/heavy", name="GET /heavy")


class AttackUser(HttpUser):
    """Simulated attacker — request liên tục không nghỉ."""
    weight = 3
    wait_time = between(0.05, 0.2)

    @task
    def flood_index(self):
        self.client.get("/", name="[ATTACK] GET /")

    @task
    def flood_heavy(self):
        self.client.get("/heavy", name="[ATTACK] GET /heavy")

    @task
    def flood_cpu(self):
        self.client.get("/cpu", name="[ATTACK] GET /cpu")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("=" * 50)
    print("Kịch bản 2: DDoS Simulation bắt đầu")
    print(f"Target: {environment.host}")
    print("Theo dõi Grafana: http://localhost:3000")
    print("AlertManager: http://localhost:9093")
    print("Agent logs: http://localhost:8080/logs")
    print("=" * 50)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n" + "=" * 50)
    print("Kịch bản 2: DDoS Simulation kết thúc")
    print("Kiểm tra Agent logs để xem AI đã xử lý gì")
    print("=" * 50)
