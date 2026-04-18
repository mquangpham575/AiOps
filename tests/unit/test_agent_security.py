import subprocess
import sys
import time
import os
import requests
import unittest

def wait_for_agent(url, timeout=10):
    """Wait for the agent to become responsive with a retry loop."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            # Check /health as it's the only unauthenticated endpoint
            requests.get(url, timeout=1)
            return True
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(0.2)
    return False

class TestAgentSecurity(unittest.TestCase):
    def test_missing_key_exits(self):
        """Verify the agent fails to start without AGENT_API_KEY."""
        print("Testing strict startup check...")
        # Use explicit PIPE instead of capture_output=True to avoid WinAPI
        # handle-duplication bug on Windows Python 3.14 when timeout is set.
        result = subprocess.run(
            [sys.executable, os.path.join(os.environ.get("BASE_DIR", "."), "src", "agent", "ai-agent", "ai_agent.py")],
            env={**os.environ, "AGENT_API_KEY": ""},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        self.assertNotEqual(result.returncode, 0, "Agent should exit when key is missing")
        # Check both stdout and stderr for reliability
        output = result.stdout + result.stderr
        self.assertIn(b"AGENT_API_KEY not set", output)
        print("✓ Strict startup check passed")

    def test_endpoint_auth(self):
        """Verify /webhook and /logs require X-Agent-Key authentication."""
        import ai_agent as agent_module

        app = agent_module.app
        app.config["TESTING"] = True

        with app.test_client() as client:
            # 1. /logs without key → 401
            r = client.get("/logs")
            self.assertEqual(r.status_code, 401)

            # 2. /logs with wrong key → 401
            r = client.get("/logs", headers={"X-Agent-Key": "wrong_key"})
            self.assertEqual(r.status_code, 401)

            # 3. /logs with correct key (set by conftest.py) → 200
            r = client.get("/logs", headers={"X-Agent-Key": "test-agent-key-12345"})
            self.assertEqual(r.status_code, 200)

            # 4. /webhook without key → 401
            r = client.post("/webhook", json={"alerts": []},
                            content_type="application/json")
            self.assertEqual(r.status_code, 401)

            # 5. /webhook with correct key and empty alerts → 200
            r = client.post("/webhook", json={"alerts": []},
                            headers={"X-Agent-Key": "test-agent-key-12345"},
                            content_type="application/json")
            self.assertEqual(r.status_code, 200)

        print("✓ Endpoint authentication passed")

if __name__ == "__main__":
    unittest.main()
