import requests
import time

PROM_URL = "http://104.215.158.157:9090/api/v1/query"
QUERY = 'container_memory_usage_bytes{name=~".*ai-agent.*"}'

print(f"--- STARTING FINAL AUDIT LOOP ---")
for i in range(5):
    try:
        r = requests.get(PROM_URL, params={'query': QUERY}, timeout=5)
        data = r.json()
        if data['status'] == 'success' and data['data']['result']:
            res = data['data']['result'][0]
            val = float(res['value'][1])
            labels = res['metric']
            print(f"[SUCCESS] Found Agent Metrics!")
            print(f"Labels: {labels}")
            print(f"Value: {val / 1024 / 1024:.2f} MB")
            exit(0)
        else:
            print(f"[WAIT] Attempt {i+1}: No data yet. Check if cAdvisor is scraped...")
    except Exception as e:
        print(f"[ERROR] {e}")
    time.sleep(5)

print("[FAIL] Could not find agent metrics after 5 attempts.")
exit(1)
