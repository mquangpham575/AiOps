# Demo 2: DDoS Attack Response

## 🎯 Objective

Demonstrate the AI agent's ability to **detect** and **respond** to DDoS (Distributed Denial of Service) attacks through intelligent analysis and automated mitigation recommendations.

## 📋 What This Demo Tests

- **Attack Detection**: Prometheus monitoring + AlertManager triggering
- **AI Analysis**: Agent's understanding of DDoS attack patterns
- **Response Time**: Speed from attack → detection → agent decision
- **Mitigation Strategy**: Agent's recommended actions (rate limiting, firewall rules)

## 🏗️ How It Works

### Attack Simulation Flow

```
Attack Script → Target App → Prometheus → AlertManager → AI Agent → Decision
   (50 req/s)     (stress)    (metrics)    (webhook)      (LLM)    (action)
```

### Timeline

1. **T+0s**: Record baseline metrics
2. **T+5s**: Launch DDoS attack (50 requests/sec for 30s)
3. **T+15s**: Prometheus detects high request rate → fires alert
4. **T+18s**: AI Agent receives webhook → analyzes alert
5. **T+20s**: Agent decides mitigation strategy
6. **T+35s**: Attack ends
7. **T+50s**: System recovery measured

## 🚀 Running the Demo

```bash
cd demos/demo2-ddos

# Make executable
chmod +x run.sh validate.sh

# Run demo
./run.sh

# Validate results
./validate.sh
```

### What You'll See

- 🚨 Real-time attack traffic generation
- 📊 Resource usage spikes in Docker stats
- 🤖 AI Agent processing webhook alerts
- ✅ Agent recommendations for mitigation

## 📊 Expected Results

### Successful Attack Detection

```
=== DURING ATTACK ===
Container Stats:
target-app    45.2%    180MB/2GB    450kB/120kB

Current Request Rate: 52.3 requests/second (baseline: 2.1)
```

### AI Agent Response

```json
{
  "alert": "HighRequestRate",
  "decision": "Implement rate limiting",
  "actions": [
    "apply_rate_limit: 100 req/min per IP",
    "enable_iptables_rate_limiting",
    "monitor_for_continued_attack"
  ],
  "confidence": 0.92
}
```

### Attack Impact

```
Total Responses: 1500
Successful (200): 1200
Rate Limited (429): 180
Errors (5xx): 120

Error Rate: 8% (acceptable under attack)
```

##✅ Validation Checks

The validation script verifies:

1. ✅ Attack was executed (pre/during/post metrics)
2. ✅ AlertManager triggered HighRequestRate alert
3. ✅ AI Agent detected and processed alert
4. ✅ Agent recommended appropriate mitigation
5. ✅ System recovered after attack
6. ✅ Error rate within acceptable limits (<10%)
7. ✅ Services remain healthy post-attack

## 📈 Viewing in Grafana

1. Open: `http://localhost:3000` (admin/admin123)
2. Dashboard: **NT531 AIOps System Overview**
3. Time range: Last 15 minutes
4. Look for:
   - **Request Rate spike** (from 2/s → 50/s)
   - **CPU usage increase** (target-app)
   - **Alert firing** (red bar)
   - **Recovery to baseline**

## 🔍 Key Metrics

| Metric             | Baseline  | During Attack | Expected     |
| ------------------ | --------- | ------------- | ------------ |
| **Request Rate**   | 2-5 req/s | 50+ req/s     | 10x increase |
| **Target CPU**     | 3-5%      | 40-50%        | 10x increase |
| **Error Rate**     | <1%       | 5-10%         | Acceptable   |
| **Agent Response** | N/A       | < 5 seconds   | Fast         |

## 💡 Learning Objectives

1. **DDoS Detection**: How monitoring systems identify attack patterns
2. **Alert Routing**: Prometheus → AlertManager → Webhook flow
3. **AI Decision Making**: LLM analysis of attack scenarios
4. **Mitigation Strategies**: Rate limiting, firewall rules, traffic shaping
5. **System Resilience**: Maintaining availability under attack

## 🛠️ Troubleshooting

### Alert Not Triggered

```bash
# Check Prometheus query
curl "http://localhost:9090/api/v1/query?query=rate(flask_http_request_total[1m])"

# Verify alert rules
docker exec prometheus cat /etc/prometheus/alert.rules.yml | grep HighRequestRate

# Check AlertManager
curl http://localhost:9093/api/v2/alerts
```

### Attack Failed to Generate Load

```bash
# Verify target app is responding
curl http://localhost:5000/health

# Check attack response log
tail -f results/attack_responses_*.log
```

## 📚 Command Reference

```bash
# Monitor attack in real-time
watch -n 1 'curl -s http://localhost:9090/api/v1/query?query=rate(flask_http_request_total[1m])'

# View agent decisions
curl http://localhost:8080/logs | jq '.[] | select(.alert | contains("HighRequest"))'

# Check current request rate
docker logs target-app --tail 50 | grep -c "GET /"
```

## 🎓 Expected Outcomes

- ✅ Attack detected within **15 seconds**
- ✅ Agent responds within **5 seconds** of receiving alert
- ✅ **>90% confidence** in decision
- ✅ Appropriate mitigation strategy recommended
- ✅ System maintains **>90% availability** during attack
- ✅ Full recovery within **30 seconds** after attack ends

---

**Previous**: [Demo 1 - Baseline Assessment](../demo1-baseline/README.md) ← | **Next**: [Demo 3 - CPU Stress](../demo3-cpu-stress/README.md) →
