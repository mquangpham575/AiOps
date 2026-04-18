import requests
import json

PROM_URL = "http://104.215.158.157:9090"

queries = {
    "agent_cpu": 'rate(container_cpu_usage_seconds_total{name="ai-agent"}[2m]) * 100',
    "agent_memory": 'container_memory_usage_bytes{name="ai-agent"}',
    "agent_cpu_regex": 'sum(rate(container_cpu_usage_seconds_total{name=~".*ai-agent.*"}[2m])) * 100',
}

print("--- DEBUGGING AGENT METRICS ---")
for name, q in queries.items():
    print(f"\nQuerying: {name}")
    try:
        r = requests.get(f"{PROM_URL}/api/v1/query", params={"query": q}, timeout=5)
        data = r.json()
        print(f"Status: {data['status']}")
        results = data.get("data", {}).get("result", [])
        if not results:
            print("  [!] NO DATA RETURNED")
        for res in results:
            print(f"  Metric Labels: {res['metric']}")
            print(f"  Value: {res['value'][1]}")
    except Exception as e:
        print(f"  [ERR] {e}")
