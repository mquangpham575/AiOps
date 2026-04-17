import requests
import json
import sys

PROMETHEUS_URL = "http://localhost:9090"

def query_prometheus(query_str):
    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query_str},
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    # Define our target queries without any escaping hell
    queries = {
        "cpu": 'rate(container_cpu_usage_seconds_total{name="target-app"}[1m]) * 100',
        "memory": 'container_memory_usage_bytes{name="target-app"} / container_spec_memory_limit_bytes{name="target-app"} * 100',
        "alerts": 'ALERTS{alertstate="firing"}',
        "all_alerts": "ALERTS",
        "targets": "up"
    }
    
    cmd = sys.argv[1] if len(sys.argv) > 1 else "alerts"
    target_query = queries.get(cmd, cmd)
    
    print(f"--- Querying: {target_query} ---")
    result = query_prometheus(target_query)
    print(json.dumps(result, indent=2))
