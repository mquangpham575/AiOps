from locust import HttpUser, task, between, events
import time

class LegitimateUser(HttpUser):
    """Simulates a normal user browsing the site."""
    wait_time = between(1, 2)
    weight = 1
    
    @task
    def visit_health(self):
        self.client.get("/health", name="Legitimate: Health")

    @task
    def visit_data(self):
        # Assuming there is a /data or just root
        self.client.get("/", name="Legitimate: Root")

class AttackerUser(HttpUser):
    """Simulates a DDoS attacker flooding the server."""
    wait_time = between(0.01, 0.05) # Very fast requests
    weight = 10
    
    @task
    def flood(self):
        self.client.get("/", name="Attack: Flood")

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Custom listener to log RPS and latency per user class."""
    # This info is normally captured by --csv, but we can log specifically if needed.
    pass
