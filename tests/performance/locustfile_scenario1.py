import time
from locust import HttpUser, task, between, events
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Scenario1User(HttpUser):
    wait_time = between(1, 2)
    
    def on_start(self):
        # We use environment variables or custom arguments if needed, 
        # but for simplicity in this demo, we can log the start.
        pass

class BaselineUser(Scenario1User):
    weight = 1
    
    @task(3)
    def index(self):
        self.client.get("/")

    @task(1)
    def health(self):
        self.client.get("/health")

class LoadUser(Scenario1User):
    weight = 10
    
    @task(2)
    def index(self):
        self.client.get("/")

    @task(1)
    def health(self):
        self.client.get("/health")

    @task(5)
    def stress_light(self):
        # Light stress to POST /stress
        self.client.post("/stress", json={"workers": 1, "timeout": 5})

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    # Log phase information to stdout as requested
    users = environment.runner.target_user_count
    phase = "Phase A" if users == 0 else "Phase B"
    # Note: run number needs to be handled by the shell wrapper
    print(f"[PHASE] {phase} started — {users} users")
