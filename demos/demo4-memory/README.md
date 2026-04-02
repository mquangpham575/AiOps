# Demo 4: Memory Exhaustion Auto-Remediation

## 🎯 Objective

Demonstrate the AI agent's ability to **automatically detect** and **respond** to memory exhaustion scenarios by analyzing memory pressure and taking intelligent remediation actions such as service restart or resource cleanup.

## 📋 What This Demo Tests

- **Memory Monitoring**: Real-time memory pressure detection via Prometheus
- **Attack Detection**: Identifying sustained high memory usage patterns
- **AI Analysis**: Agent's understanding of memory stress scenarios
- **Auto-Remediation**: Automatic service restart or memory cleanup
- **Validation Logic**: Pre-action checks to ensure safe remediation

## 🏗️ How It Works

### Memory Exhaustion Flow

```
Memory Requests → High Memory → Prometheus → AlertManager → AI Agent → Analysis
  (20 MB/req)     (metric)     (monitors)   (fires alert)   (receives)  (action)
                                                                 ↓
                                                          Remediation
                                                          (restart/cleanup)
                                                                 ↓
                                                          Memory Recovery
```

### Timeline

1. **T+0s**: Record memory baseline (~30-40%)
2. **T+10s**: Launch memory exhaustion via Locust MemoryStressUser
3. **T+20s**: Memory usage climbs steadily (20 MB per request)
4. **T+35s**: Prometheus detects high memory → triggers HighMemoryUsage alert
5. **T+40s**: AI Agent receives alert webhook
6. **T+42s**: Agent analyzes memory trend → identifies service for restart
7. **T+45s**: Agent triggers service restart (via restart_service tool)
8. **T+50s**: Service reboots, memory cleared
9. **T+60s**: Memory returns to baseline (~35%)

## 🚀 Running the Demo

```bash
cd demos/demo4-memory

# Make scripts executable
chmod +x run.sh validate.sh

# Run the demo
./run.sh

# Validate auto-remediation
./validate.sh
```

### What You'll See

- 📊 Real-time memory usage spike in Docker stats
- 🚨 Memory exhaustion alerts from Prometheus
- 🤖 AI Agent analyzing alert and making decision
- ✅ Automatic service restart execution
- 📉 Memory returning to normal levels

## 📊 Expected Results

### Memory Baseline (Before Attack)

```
=== BASELINE MEMORY USAGE ===
target-app    2.8% CPU    380MB/2GB    15 PIDs

Prometheus Memory Rate: 38% (of 2GB total)
```

### During Memory Stress

```
=== DURING STRESS ===
target-app    12.4% CPU    1.8GB/2GB    25 PIDs

Memory Pressure:
  MemTotal: 2048 MB
  MemAvailable: 250 MB
  MemUsed: 1800 MB
  Pressure: 87.8%

Active Memory Requests:
- /memory?mb=20 (x20 concurrent users)
- Total memory allocation: 400 MB/request cycle
```

### AI Agent Decision

```json
{
  "timestamp": "2026-03-24T12:34:56Z",
  "alert": "HighMemoryUsage",
  "decision": "Restart target service to clear memory",
  "reasoning": "Memory usage at 87% with sustained pressure - service restart will clear caches and free allocated memory",
  "tool_used": "restart_service",
  "actions": [
    "validate_service_state: target-app",
    "analyze_memory_trend: sustained high usage",
    "restart_service: target-app",
    "verify_service_health: post-restart"
  ],
  "confidence": 0.88,
  "result": "SUCCESS: Service restarted, memory freed"
}
```

### Post-Remediation

```
=== POST-REMEDIATION MEMORY CHECK ===
Service Status: Running
Memory Usage: 420MB/2GB (20.5%)

SUCCESS: Service restarted and memory recovered!
```

### Recovery

```
=== FINAL RECOVERY STATE ===
target-app    3.1% CPU    390MB/2GB    16 PIDs

Memory returned to baseline - full recovery achieved
```

## ✅ Validation Checks

The validation script verifies:

1. ✅ Memory stress was initiated (high memory requests)
2. ✅ Memory usage increased significantly (>80%)
3. ✅ Prometheus triggered HighMemoryUsage alert
4. ✅ AI Agent detected the alert
5. ✅ Agent decided to restart service
6. ✅ **Service was successfully restarted**
7. ✅ Memory returned to baseline (<50%)
8. ✅ Service is healthy and responsive post-restart

### Validation Score

```bash
./validate.sh

# Expected output:
Validation Score: 8/8 (100%)

✅ EXCELLENT - AUTO-REMEDIATION SUCCESSFUL!

✓ Memory stress was successfully created
✓ AI Agent detected the alert
✓ Agent automatically restarted the service
✓ System recovered to normal state
✓ Service remains healthy
```

## 🧠 Enhanced Intelligence Features

### 1. Memory Trend Analysis

The agent recognizes memory exhaustion patterns:

- **Sustained High Memory**: Indicates actual leak or pressure, not temporary spike
- **Memory Climbing**: Gradual increase suggests ongoing allocation
- **Threshold Breach**: >80% of available memory indicates critical condition

### 2. Multi-Step Workflow

```python
# Agent's automatic workflow:
1. validate_service_state("target-app")      # Pre-check
2. analyze_memory_trend()                    # Pattern analysis
3. evaluate_remediation_options()            # Cost-benefit
4. restart_service("target-app")             # Execution
5. verify_service_health()                   # Post-check
6. confirm_memory_recovery()                 # Validation
```

### 3. Intelligent Decision Making

- **Decides to restart** when: Sustained pressure + no obvious leak
- **Alternative**: Could trigger cleanup or process termination
- **Validates** service can be restarted safely (not critical path)
- **Verifies** service is healthy after restart

## 📈 Viewing in Grafana

1. Open: `http://localhost:3000` (admin/admin123)
2. Dashboard: **NT531 AIOps System Overview**
3. Time range: Last 15 minutes
4. Key panels:
   - **Memory Usage**: See spike and recovery
   - **Memory Pressure**: Percentage of available memory
   - **Service Status**: Health indicator
   - **Alert Timeline**: Red bar when alert fires
   - **Agent Actions**: Decision log entries

## 🔍 Key Metrics Comparison

| Phase           | Mem %   | Avail | Requests | Status       |
| --------------- | ------- | ----- | -------- | ------------ |
| **Baseline**    | 35%     | 1.3GB | 0        | ✅ Normal    |
| **Attack**      | 87%     | 260MB | 20/sec   | 🔥 Critical  |
| **Remediation** | 65%     | 700MB | 0        | ⚙️ Resolving |
| **Recovery**    | 37%     | 1.3GB | 0        | ✅ Resolved  |

## 💡 Learning Objectives

1. **Memory Management**: How to monitor and respond to memory pressure
2. **AI Decision Making**: LLM reasoning about system health
3. **Auto-Remediation**: Autonomous service restart without humans
4. **Docker Integration**: Using Docker API for service control
5. **Trend Analysis**: Detecting sustained vs. temporary conditions
6. **Health Checks**: Verifying services remain functional post-action

## 🛠️ Troubleshooting

### Alert Not Triggered

```bash
# Check current memory
docker stats target-app --no-stream

# Verify memory requests
curl -s http://localhost:8080/logs | jq '.[] | select(.alert | contains("Memory"))'

# Check Prometheus alert rule
curl "http://localhost:9090/api/v1/query?query=node_memory_MemTotal_bytes-node_memory_MemAvailable_bytes"
```

### Agent Didn't Restart Service

```bash
# Check agent logs
curl http://localhost:8080/logs | jq

# Verify agent received alert
curl http://localhost:9093/api/v1/alerts | jq '.data[] | select(.labels.alertname=="HighMemoryUsage")'

# Check service status
docker ps | grep target-app
```

### Memory Didn't Return to Baseline

```bash
# Check if service is running
docker exec target-app pgrep -f "python" | wc -l

# Check for memory leaks
docker stats target-app --no-stream

# Force restart if needed
docker restart target-app
```

## 📚 Command Reference

```bash
# Watch memory in real-time
watch -n 1 'docker stats target-app --no-stream'

# Monitor memory pressure
watch -n 1 'docker exec target-app free -h'

# View agent decisions about memory
curl http://localhost:8080/logs | jq '.[] | select(.alert | contains("Memory"))'

# Check service health
curl http://localhost:5000/health | jq

# Query memory metrics
curl "http://localhost:9090/api/v1/query?query=container_memory_usage_bytes{name=\"target-app\"}"
```

## 🎓 Expected Outcomes

- ✅ Memory spike to **>80%** confirmed
- ✅ Agent detects within **10 seconds** of alert
- ✅ **Service restart** initiated automatically
- ✅ Service becomes **responsive** post-restart
- ✅ Memory recovery within **30 seconds**
- ✅ Agent confidence **>85%**
- ✅ **Zero manual intervention** required
- ✅ System stability maintained throughout

### Academic Value

This demo demonstrates:

1. **Autonomous Operations**: AI making and executing decisions without human approval
2. **Health Monitoring**: Proactive detection and response to resource exhaustion
3. **Service Orchestration**: Integration with container management
4. **Production-Ready**: Real service restart and recovery
5. **Measurable Results**: Clear before/after metrics
6. **Advanced Features**: Trend analysis, health checks, intelligent decisions

## 🏆 Success Criteria

Demo is successful if:

- [x] Memory stress created (high memory requests)
- [x] Memory usage exceeded 80%
- [x] Alert triggered in AlertManager
- [x] Agent detected HighMemoryUsage alert
- [x] Agent decided to restart service
- [x] **Service was restarted successfully**
- [x] Memory returned to <50%
- [x] Service is healthy and responsive
- [x] No errors or system crashes

---

**Previous**: [Demo 3 - CPU Stress Response](../demo3-cpu-stress/README.md) ← | **Main**: [Demos Overview](../README.md) ↑
