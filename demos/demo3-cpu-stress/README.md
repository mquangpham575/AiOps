# Demo 3: CPU Stress Auto-Remediation

> Archived: the legacy `demos/*/run.sh` + `validate.sh` scripts were removed. Use `python scripts/demo_runner.py --scenario cpu` (and see `DEMO_GUIDE.md` / `scenarios/README.md`).

## 🎯 Objective

Demonstrate the AI agent's ability to **automatically identify** and **kill problematic processes** causing high CPU usage. This showcases intelligent process matching, multi-step workflows, and autonomous remediation.

## 📋 What This Demo Tests

- **Process Detection**: Identifying CPU-intensive processes
- **Intelligent Matching**: Agent's ability to match process names (stress-ng, stress, etc.)
- **Auto-Remediation**: Automatic process termination without human intervention
- **Multi-Step Workflow**: Using enhanced tools like `auto_kill_cpu_stress`
- **Validation Logic**: Pre-action checks to prevent failed operations

## 🏗️ How It Works

### Remediation Workflow

```
stress-ng → High CPU → Prometheus → AlertManager → AI Agent → Process Analysis
  (attack)   (metric)   (monitors)   (fires alert)   (receives)  (identifies PID)
                                                          ↓
                                                    Kill Process
                                                          ↓
                                                    Verify Success
                                                          ↓
                                                   System Recovery
```

### Timeline

1. **T+0s**: Record CPU baseline (~3%)
2. **T+10s**: Launch stress-ng with 4 CPU workers
3. **T+20s**: CPU spikes to 80%+
4. **T+35s**: Prometheus detects sustained high CPU → triggers alert
5. **T+40s**: AI Agent receives HighCPUUsage alert
6. **T+42s**: Agent analyzes → identifies stress-ng processes
7. **T+45s**: Agent kills stress-ng (using auto_kill_cpu_stress tool)
8. **T+50s**: Verification: stress processes terminated
9. **T+80s**: CPU returns to baseline (~3%)

## 🚀 Running the Demo

This demo is now driven by the scenario runner.

```bash
# Runs the CPU remediation scenario and exports results.
python scripts/demo_runner.py --scenario cpu

# Optional: export to a specific file
python scripts/demo_runner.py --scenario cpu --export results.csv
```

### What You'll See

- 🔥 CPU usage spike in container stats
- 📊 Real-time monitoring of stress-ng processes
- 🤖 AI Agent analyzing alert and making decision
- ✅ Automatic process termination
- 📉 CPU returning to normal

## 📊 Expected Results

### CPU Baseline (Before Attack)

```
=== BASELINE CPU USAGE ===
target-app    2.8%    118MB/2GB    15 PIDs

Prometheus CPU Rate: 0.028 (2.8%)
```

### During Stress Attack

```
=== DURING STRESS ===
target-app    86.4%    125MB/2GB    20 PIDs

Active Stress Processes:
root        1234  85.2  1.1  stress-ng --cpu 4
root        1235  84.9  1.0  stress-ng-cpu [run]
root        1236  85.1  1.0  stress-ng-cpu [run]
root        1237  84.7  1.0  stress-ng-cpu [run]
root        1238  85.3  1.0  stress-ng-cpu [run]
```

### AI Agent Decision

```json
{
  "timestamp": "2026-03-24T12:34:56Z",
  "alert": "HighCPUUsage",
  "decision": "Terminate CPU stress processes",
  "reasoning": "Detected stress-ng processes consuming 85% CPU - likely stress test or attack",
  "tool_used": "auto_kill_cpu_stress",
  "actions": [
    "validate_container_exists: target-app",
    "list_processes: stress-ng, stress",
    "kill_process: stress-ng (PIDs: 1234, 1235, 1236, 1237, 1238)"
  ],
  "confidence": 0.95,
  "result": "SUCCESS: 5 processes terminated"
}
```

### Post-Remediation

```
=== POST-REMEDIATION PROCESS CHECK ===
Current Processes: No stress processes found

SUCCESS: All stress processes were terminated by AI Agent!
```

### Recovery

```
=== FINAL RECOVERY STATE ===
target-app    3.2%    119MB/2GB    15 PIDs

CPU returned to baseline - full recovery achieved
```

## ✅ Validation Checks

Use the runner output (stdout + CSV) as the validation artifact. It covers:

1. ✅ CPU stress was initiated (stress-ng running)
2. ✅ CPU usage spiked (>80%)
3. ✅ Prometheus triggered HighCPUUsage alert
4. ✅ AI Agent detected the alert
5. ✅ Agent identified stress-ng processes
6. ✅ **Agent successfully terminated processes**
7. ✅ CPU returned to baseline (<10%)
8. ✅ NO stress processes remain

### Validation Score

The summary row (`iteration=summary`) contains mean±stdev for MTTR breakdown.

## 🧠 Enhanced Intelligence Features

### 1. Intelligent Process Matching

The agent recognizes various process name patterns:

- `stress-ng` (exact match)
- `stress-ng-cpu` (variant)
- `stress` (synonym)
- Handles process trees and child processes

### 2. Multi-Step Workflow

```python
# Agent's automatic workflow:
1. validate_container_exists("target-app")  # Pre-check
2. list_processes_in_container("target-app")  # Discovery
3. identify_stress_processes()  # Pattern matching
4. kill_processes_by_pattern("stress")  # Execution
5. verify_termination()  # Post-check
```

### 3. Validation Logic

- Checks container exists before attempting commands
- Verifies processes exist before killing
- Confirms termination was successful
- Prevents failed operations and errors

## 📈 Viewing in Grafana

1. Open Grafana (loadgen VM): `http://<AZURE_LOADGEN_IP>:3000`
2. Dashboard: **NT531 AIOps System Overview**
3. Time range: Last 15 minutes
4. Key panels:
   - **CPU Usage**: See spike and recovery
   - **Process Count**: Watch PIDs increase/decrease
   - **Alert Timeline**: Red bar when alert fires
   - **Agent Actions**: Decision log entries

## 🔍 Key Metrics Comparison

| Phase           | CPU % | PIDs | Stress Procs | Status       |
| --------------- | ----- | ---- | ------------ | ------------ |
| **Baseline**    | 3%    | 15   | 0            | ✅ Normal    |
| **Attack**      | 85%   | 20   | 5            | 🔥 Critical  |
| **Remediation** | 45%   | 18   | 2            | ⚙️ Resolving |
| **Recovery**    | 3%    | 15   | 0            | ✅ Resolved  |

## 💡 Learning Objectives

1. **Process Management**: How to identify and terminate processes in containers
2. **AI Decision Making**: LLM reasoning about process patterns
3. **Auto-Remediation**: Autonomous problem resolution without humans
4. **Docker Integration**: Using Docker API for container operations
5. **Validation Importance**: Pre/post-checks prevent failed actions
6. **Synonym Recognition**: AI understanding of related terms (stress-ng ≈ stress)

## 🛠️ Troubleshooting

### Alert Not Triggered

```bash
# Check current CPU
docker stats target-app --no-stream

# Verify stress is running
docker exec target-app ps aux | grep stress

# Check Prometheus alert rule
curl "http://localhost:9090/api/v1/query?query=rate(process_cpu_seconds_total[1m])*100"
```

### Agent Didn't Kill Processes

```bash
# Check agent logs
curl http://localhost:8080/logs | jq

# Verify agent received alert
curl http://localhost:9093/api/v1/alerts | jq '.data[] | select(.labels.alertname=="HighCPUUsage")'

# Manually kill if needed
docker exec target-app pkill -9 stress-ng
```

### Stress Test Failed to Start

```bash
# Verify stress-ng exists
docker exec target-app which stress-ng

# Install if missing
docker exec target-app apt-get update && apt-get install -y stress-ng

# Run manually
docker exec target-app stress-ng --cpu 4 --timeout 30s
```

## 📚 Command Reference

```bash
# Watch CPU in real-time
watch -n 1 'docker stats target-app --no-stream'

# Monitor processes
watch -n 1 'docker exec target-app ps aux | grep stress'

# View agent decisions about CPU
curl http://localhost:8080/logs | jq '.[] | select(.alert | contains("CPU"))'

# Force kill all stress processes
docker exec target-app pkill -9 stress
```

## 🎓 Expected Outcomes

- ✅ CPU spike to **>80%** confirmed
- ✅ Agent detects within **10 seconds** of alert
- ✅ **100% process termination** success rate
- ✅ Agent confidence **>90%**
- ✅ CPU recovery within **30 seconds**
- ✅ **Zero manual intervention** required
- ✅ System stability maintained throughout

### Academic Value

This demo demonstrates:

1. **Autonomous Operations**: AI making and executing decisions without human approval
2. **Intelligent Reasoning**: LLM understanding process relationships
3. **Production-Ready**: Real container and process management
4. **Measurable Results**: Clear before/after metrics
5. **Advanced Features**: Multi-step workflows, validation logic, error handling

## 🏆 Success Criteria

Demo is successful if:

- [x] Stress processes created (verified in ps aux)
- [x] CPU usage exceeded 80%
- [x] Alert triggered in AlertManager
- [x] Agent detected HighCPUUsage alert
- [x] Agent identified stress-ng processes
- [x] **All stress processes killed**
- [x] CPU returned to <10%
- [x] No errors or system crashes

---

**Previous**: [Demo 2 - DDoS Response](../demo2-ddos/README.md) ← | **Main**: [Demos Overview](../README.md) ↑
