"""
locustfile.py — AIOps Performance Evaluation Load Test
=====================================================

MỤC TIÊU ĐÁNH GIÁ:
  - So sánh hiệu năng baseline vs stress (intra-run comparison)
  - Đo latency percentiles (p50, p95, p99) dưới tải khác nhau
  - Đánh giá overhead của AI Agent lên hệ thống
  - Đo throughput và error rate dưới various load profiles

TARGET METRICS (Prometheus):
  - flask_http_request_duration_seconds (histogram) → latency percentiles
  - flask_http_requests_total (counter) → throughput
  - container_cpu_usage_seconds_total → CPU usage
  - container_memory_usage_bytes → Memory usage

TAG MAPPING:
  baseline    → NormalUser tasks only (light load, baseline measurement)
  ddos        → NormalUser + AttackUser tasks (DDoS simulation)
  memory      → MemoryStressUser tasks (memory exhaustion test)
  legi_attack → LegitimateUser + AttackUser tasks (DDoS trade-off analysis)

CÁCH CHẠY:
  # Baseline measurement
  ATTACK_PROFILE=baseline locust -f tests/performance/locustfile.py \
    --host=http://<IP> --run-time 300s --headless --tags baseline

  # DDoS scenario
  ATTACK_PROFILE=ddos locust -f tests/performance/locustfile.py \
    --host=http://<IP> --run-time 300s --headless --tags ddos

  # Memory stress
  ATTACK_PROFILE=memory locust -f tests/performance/locustfile.py \
    --host=http://<IP> --run-time 300s --headless --tags memory

  # DDoS trade-off (legitimate users vs attackers)
  locust -f tests/performance/locustfile.py \
    --host=http://<IP> --run-time 300s --headless --tags legi_attack

EXPECTED RESULTS:
  - Baseline: p50 < 50ms, p95 < 100ms, p99 < 200ms
  - Under load: p95 increases 2-5x depending on system capacity
  - Memory: Sustained allocation triggers container restart

PROFILES (StagedLoadShape):
  baseline: Stable 20 users
  ddos: 50 → 500 users (warm-up → ramp → peak)
  memory: 5 → 20 users (sustained memory allocation)
"""

from locust import HttpUser, LoadTestShape, task, between, events, tag
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Staged attack profiles ────────────────────────────────────────────────────
# Each tuple: (start_time_s, target_users, spawn_rate)
# The last entry with target_users=None signals end of test.
_PROFILES: dict[str, list[tuple]] = {
    "baseline": [
        # Stable baseline load — low and steady for baseline measurement.
        # Runtime controlled by --run-time flag.
        (0, 20, 2),
        (3600, None, 0),
    ],
    "ddos": [
        # Instant spike: 500 users reached at 100/s
        (0, 500, 100),
        (120, None, 0),
    ],
    "memory": [
        # Memory exhaustion: sustained allocation to trigger OOM
        (0, 5, 1),  # warm-up:   5 users, ramp at 1/s
        (30, 20, 2),  # ramp:     20 users, ramp at 2/s
        (90, 20, 5),  # peak:     20 users, sustained allocation
        (180, None, 0),  # stop
    ],
    "cpu_flood": [
        # Sustained CPU exhaustion via /cpu endpoint
        (0, 10, 2),   # warm-up
        (30, 100, 10), # ramp to 100 concurrent hitters
        (180, None, 0), # stop
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
        
        # Respect --run-time CLI flag if set
        if hasattr(self.runner.environment.parsed_options, "run_time") and self.runner.environment.parsed_options.run_time:
            if run_time > self.runner.environment.parsed_options.run_time:
                return None

        # Walk stages in reverse to find the active one
        for start_t, users, spawn_rate in reversed(self._stages):
            if run_time >= start_t:
                if users is None:
                    return None  # signal Locust to stop
                return (users, spawn_rate)
        # Before first stage — fallback to stage 0
        return (self._stages[0][1], self._stages[0][2])


# ── User Classes ─────────────────────────────────────────────────────────────


class NormalUser(HttpUser):
    """
    Normal user thông thường — cho baseline và DDoS scenarios.

    Hành vi:
      - GET / (weight=3): Trang chủ chính
      - GET /heavy (weight=1): Endpoint nặng, mô phỏng slow query
      - GET /health (weight=1): Health check

    Tags: baseline, ddos
    """

    weight = 1
    wait_time = between(0.5, 1.5)

    @tag("baseline", "ddos")
    @task(3)
    def index(self):
        """Trang chủ — endpoint chính để test throughput."""
        self.client.get("/", name="GET /")

    @tag("baseline", "ddos")
    @task(1)
    def heavy(self):
        """Endpoint nặng — mô phỏng slow response để test latency."""
        self.client.get("/heavy", name="GET /heavy")

    @tag("baseline")
    @task(1)
    def health(self):
        """Health check — baseline profile only."""
        self.client.get("/health", name="GET /health")


from locust.contrib.fasthttp import FastHttpUser

class AttackUser(FastHttpUser):
    """
    Attacker - Extremely aggressive flood for Scenario 1.
    Uses FastHttp to maximize throughput.
    Tags: ddos, legi_attack
    """
    wait_time = between(0, 0)
    weight = 10

    @tag("ddos", "cpu_flood")
    @task
    def flood_attack(self):
        self.client.get("/", name="/ (DDOS)")
    wait_time = between(0.01, 0.05)

    @tag("baseline", "ddos", "memory", "cpu_flood", "legi_attack")
    @task(1)
    def dummy(self):
        """No-op task to prevent Locust errors when filtered by tag."""
        pass

    @tag("ddos", "legi_attack")
    @task
    def flood_index(self):
        """Flood trang chủ — primary attack vector."""
        self.client.get("/", name="[ATTACK] GET /")

    @tag("ddos", "legi_attack")
    @task
    def flood_heavy(self):
        """Flood /heavy endpoint — amplify server load."""
        self.client.get("/heavy", name="[ATTACK] GET /heavy")

    @tag("ddos")
    @task
    def flood_cpu(self):
        """Flood /cpu endpoint — CPU intensive attack."""
        self.client.get("/cpu", name="[ATTACK] GET /cpu")


_MEMORY_MB = int(os.environ.get("MEMORY_MB_PER_REQUEST", "20"))


class MemoryStressUser(HttpUser):
    """
    Memory stress user — exhaust container memory.

    Hành vi:
      - Continuous /memory calls với configurable size (default 20MB)
      - Wait time ngắn (0.1-0.3s) để sustain pressure
      - Container sẽ OOM và restart nếu memory limit thấp

    Tags: memory

    Target metrics:
      - container_memory_usage_bytes
      - container_restart_count
    """

    weight = 2
    wait_time = between(0.1, 0.3)

    @tag("baseline", "ddos", "memory", "cpu_flood", "legi_attack")
    @task(1)
    def dummy(self):
        """No-op task to prevent Locust errors when filtered by tag."""
        pass

    @tag("memory")
    @task
    def exhaust_memory(self):
        """Allocate and hold memory — triggers OOM under sustained load."""
        self.client.get(f"/memory?mb={_MEMORY_MB}", name="[MEMORY] GET /memory")


class CPUFloodUser(HttpUser):
    """
    Dedicated CPU flood user — targets the /cpu endpoint exclusively.
    """
    weight = 5
    wait_time = between(0.01, 0.05)

    @tag("baseline", "ddos", "memory", "cpu_flood", "legi_attack")
    @task(1)
    def dummy(self):
        """No-op task to prevent Locust errors when filtered by tag."""
        pass

    @tag("cpu_flood")
    @task
    def flood_cpu(self):
        """Rapid fire /cpu requests."""
        self.client.get("/cpu", name="[CPU-FLOOD] GET /cpu")


class LegitimateUser(HttpUser):
    """
    Legitimate user — cho DDoS trade-off analysis.

    Hành vi:
      - Normal browsing pattern (wait 1-2s)
      - Low weight (1) để represent real users
      - Target endpoints: /, /health, /data

    Tags: legi_attack

    Dùng trong scenario 3 để đo:
      - Legitimate user success rate under attack
      - Collateral damage from rate limiting
    """

    weight = 1
    wait_time = between(1, 2)

    @tag("baseline", "ddos", "memory", "cpu_flood", "legi_attack")
    @task(1)
    def dummy(self):
        """No-op task to prevent Locust errors when filtered by tag."""
        pass

    @tag("legi_attack")
    @task
    def visit_health(self):
        """Legitimate: health check."""
        self.client.get("/health", name="Legit: GET /health")

    @tag("legi_attack")
    @task
    def visit_index(self):
        """Legitimate: browse main page."""
        self.client.get("/", name="Legit: GET /")

    @tag("legi_attack")
    @task
    def visit_heavy(self):
        """Legitimate: occasional slow request."""
        self.client.get("/heavy", name="Legit: GET /heavy")


# ── Event Listeners ───────────────────────────────────────────────────────────


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Log test configuration khi bắt đầu."""
    profile = os.environ.get("ATTACK_PROFILE", "ddos")
    tags = (
        environment.runner.host_tags
        if hasattr(environment.runner, "host_tags")
        else "N/A"
    )

    logger.info("=" * 60)
    logger.info(f"AIOps Load Test starting")
    logger.info(f"  Profile:    {profile}")
    logger.info(f"  Target:     {environment.host}")
    logger.info(f"  Tags:       {tags}")
    logger.info(f"  Run time:   {environment.runner.target_user_count}s (if specified)")
    logger.info("=" * 60)
    print(f"[LOCUST] Test started — profile: {profile}, target: {environment.host}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Log summary khi test kết thúc."""
    stats = environment.stats
    total_rps = stats.total.rps
    total_failures = stats.total.fail_count
    total_requests = stats.total.num_requests

    logger.info("=" * 60)
    logger.info("AIOps Load Test finished")
    logger.info(f"  Total requests:  {total_requests}")
    logger.info(f"  Total failures:  {total_failures}")
    logger.info(f"  Average RPS:     {total_rps:.2f}")
    logger.info(
        f"  p50 latency:     {stats.total.get_response_time_percentile(0.5):.1f}ms"
    )
    logger.info(
        f"  p95 latency:     {stats.total.get_response_time_percentile(0.95):.1f}ms"
    )
    logger.info(
        f"  p99 latency:     {stats.total.get_response_time_percentile(0.99):.1f}ms"
    )
    logger.info("=" * 60)
    print(
        f"[LOCUST] Test completed — RPS: {total_rps:.1f}, p95: {stats.total.get_response_time_percentile(0.95):.0f}ms"
    )


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Log per-request events for debugging (optional)."""
    if exception:
        logger.warning(f"Request failed: {name} - {exception}")
