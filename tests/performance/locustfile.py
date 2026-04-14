"""
locustfile.py — Load test scenarios for AIOps evaluation.

Cách chạy (từ thư mục gốc):
  # DDoS scenario (staged: warm-up → ramp → peak over 3 min):
  ATTACK_PROFILE=ddos locust -f loadtest/locustfile.py \
    --host=http://<AZURE_VM_IP> --run-time 3m --headless --tags ddos

  # Memory scenario (staged: warm-up → ramp → peak over 3 min):
  ATTACK_PROFILE=memory locust -f loadtest/locustfile.py \
    --host=http://<AZURE_VM_IP> --run-time 3m --headless --tags memory

  # UI mode (manual exploration — no ATTACK_PROFILE needed):
  locust -f loadtest/locustfile.py --host=http://<AZURE_VM_IP>

NOTE: StagedLoadShape overrides --users / --spawn-rate CLI flags.
      demo_runner.py passes ATTACK_PROFILE automatically via env=.

Metrics tracked in Grafana:
  - flask_http_request_duration_seconds (latency)
  - flask_http_requests_total (throughput)
  - node_network_receive_bytes_total (bandwidth)
"""

from locust import HttpUser, LoadTestShape, task, between, events, tag
import os

# ── Staged attack profiles ────────────────────────────────────────────────────
# Each tuple: (start_time_s, target_users, spawn_rate)
# The last entry with target_users=None signals end of test.
_PROFILES: dict[str, list[tuple]] = {
    "baseline": [
        # Stable baseline load used for baseline-vs-ddos comparisons.
        # Intentionally low and steady; runtime is controlled by --run-time.
        (0,   20,  2),
        (3600, None, 0),
    ],
    "ddos": [
        (0,   50,  3),    # warm-up:  50 users, ramp at  3/s for 30s
        (30,  500, 10),   # ramp:    500 users, ramp at 10/s for 60s
        (90,  500, 50),   # peak:    500 users, hold at 50/s for 90s
        (180, None, 0),   # stop
    ],
    "memory": [
        (0,   5,  1),     # warm-up:   5 users, ramp at 1/s for 30s
        (30,  20, 2),     # ramp:     20 users, ramp at 2/s for 60s
        (90,  20, 5),     # peak:     20 users, hold at 5/s for 90s
        (180, None, 0),   # stop
    ],
}


class StagedLoadShape(LoadTestShape):
    """
    Multi-phase load shape: warm-up → ramp → peak.
    Selected via ATTACK_PROFILE env var (default: "ddos").

    Overrides --users / --spawn-rate CLI flags when present.
    demo_runner.py passes ATTACK_PROFILE via env= in Popen.
    """
    _profile_name = os.environ.get("ATTACK_PROFILE", "ddos")
    _stages = _PROFILES.get(_profile_name, _PROFILES["ddos"])

    def tick(self) -> tuple[int, float] | None:
        run_time = self.get_run_time()
        # Walk stages in reverse to find the active one
        for start_t, users, spawn_rate in reversed(self._stages):
            if run_time >= start_t:
                if users is None:
                    return None  # signal Locust to stop
                return (users, spawn_rate)
        # Before first stage — should not happen but return stage 0 as fallback
        return (self._stages[0][1], self._stages[0][2])


class NormalUser(HttpUser):
    """User thông thường — weight cao hơn."""
    weight = 1
    wait_time = between(0.5, 1.5)

    @tag("ddos", "baseline")
    @task(3)
    def index(self):
        self.client.get("/", name="GET /")

    @tag("ddos", "baseline")
    @task(1)
    def heavy(self):
        self.client.get("/heavy", name="GET /heavy")


class AttackUser(HttpUser):
    """Simulated attacker — request liên tục không nghỉ."""
    weight = 3
    wait_time = between(0.05, 0.2)

    @tag("ddos")
    @task
    def flood_index(self):
        self.client.get("/", name="[ATTACK] GET /")

    @tag("ddos")
    @task
    def flood_heavy(self):
        self.client.get("/heavy", name="[ATTACK] GET /heavy")

    @tag("ddos")
    @task
    def flood_cpu(self):
        self.client.get("/cpu", name="[ATTACK] GET /cpu")


_MEMORY_MB = int(os.environ.get("MEMORY_MB_PER_REQUEST", "20"))


class MemoryStressUser(HttpUser):
    """Scenario 4: Memory exhaustion — repeated /memory calls sustain container memory pressure."""
    weight = 2
    wait_time = between(0.1, 0.3)

    @tag("memory")
    @task
    def exhaust_memory(self):
        self.client.get(f"/memory?mb={_MEMORY_MB}", name="[MEMORY] GET /memory")


# ── Scenario usage ──────────────────────────────────────────────────────────
# Staged shape is active whenever StagedLoadShape class is in the file.
# demo_runner.py passes ATTACK_PROFILE=ddos or ATTACK_PROFILE=memory via env=.
# Without ATTACK_PROFILE, defaults to "ddos" profile.


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    profile = os.environ.get("ATTACK_PROFILE", "ddos")
    print("=" * 50)
    print(f"AIOps Load Test starting — profile: {profile}")
    print(f"Target: {environment.host}")
    print("Grafana:      http://localhost:3000")
    print("AlertManager: http://localhost:9093")
    print("Agent logs:   http://localhost:8080/logs/ui")
    print("=" * 50)


@events.test_stop.add_listener
def on_test_stop(**kwargs):
    print("\n" + "=" * 50)
    print("AIOps Load Test finished.")
    print("Check agent log: http://localhost:8080/logs/ui")
    print("=" * 50)
