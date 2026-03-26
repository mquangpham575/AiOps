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
        result = subprocess.run(
            [sys.executable, "agent/agent.py"],
            env={**os.environ, "AGENT_API_KEY": ""},
            capture_output=True,
            timeout=5
        )
        self.assertNotEqual(result.returncode, 0, "Agent should exit when key is missing")
        # Check both stdout and stderr for reliability
        output = result.stdout + result.stderr
        self.assertIn(b"AGENT_API_KEY not set", output)
        print("✓ Strict startup check passed")

    def test_endpoint_auth(self):
        """Verify /webhook and /logs require authentication."""
        print("Testing endpoint authentication...")
        # Start agent in background with a test key
        test_key = "secure_test_key"
        proc = subprocess.Popen(
            [sys.executable, "agent/agent.py"],
            env={**os.environ, "AGENT_API_KEY": test_key}
        )
        
        try:
            # Wait for agent to start using retry loop (flakiness prevention)
            if not wait_for_agent("http://localhost:8080/health"):
                self.fail("Agent did not become responsive within timeout")
            
            # 1. Test /logs without key
            r = requests.get("http://localhost:8080/logs")
            self.assertEqual(r.status_code, 401)
            
            # 2. Test /logs with wrong key
            r = requests.get("http://localhost:8080/logs", headers={"X-Agent-Key": "wrong"})
            self.assertEqual(r.status_code, 401)
            
            # 3. Test /logs with correct key
            r = requests.get("http://localhost:8080/logs", headers={"X-Agent-Key": test_key})
            self.assertEqual(r.status_code, 200)
            
            # 4. Test /webhook without key
            r = requests.post("http://localhost:8080/webhook", json={"alerts":[]})
            self.assertEqual(r.status_code, 401)
            
            # 5. Test /webhook with correct key
            r = requests.post("http://localhost:8080/webhook", 
                              headers={"X-Agent-Key": test_key},
                              json={"alerts":[]})
            self.assertEqual(r.status_code, 200)
            
            print("✓ Endpoint authentication passed")
            
        finally:
            proc.terminate()
            proc.wait()

if __name__ == "__main__":
    unittest.main()
