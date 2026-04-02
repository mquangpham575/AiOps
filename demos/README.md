# 🎮 AIOps Demos - Interactive Testing & Validation

Welcome to the NT531 AIOps demonstration suite! This folder contains **4 comprehensive demos** that showcase the system's intelligent monitoring, detection, and auto-remediation capabilities.

## 📁 Demo Structure

```
demos/
├── README.md                    ← You are here
├── run-all-demos.sh            ← Run all 4 demos sequentially
├── demo1-baseline/             ← Measures AI agent overhead
│   ├── run.sh                  ← Execute baseline test
│   ├── validate.sh             ← Validate results
│   ├── README.md               ← Detailed documentation
│   └── results/                ← Generated results files
├── demo2-ddos/                 ← DDoS attack response
│   ├── run.sh                  ← Execute DDoS simulation
│   ├── validate.sh             ← Validate attack detection
│   ├── README.md               ← Detailed documentation
│   └── results/                ← Attack logs & results
├── demo3-cpu-stress/           ← Auto-remediation of CPU stress
│   ├── run.sh                  ← Execute CPU stress test
│   ├── validate.sh             ← Validate auto-kill success
│   ├── README.md               ← Detailed documentation
│   └── results/                ← Process & CPU logs
└── demo4-memory/               ← Auto-remediation of memory exhaustion
    ├── run.sh                  ← Execute memory stress test
    ├── validate.sh             ← Validate service recovery
    ├── README.md               ← Detailed documentation
    └── results/                ← Memory & recovery logs
```

---

## 🎯 Demo Overview

### Demo 1: Baseline Performance Assessment

**Objective**: Measure the overhead of the AI agent on system resources

**What it demonstrates**:

- AI agent resource consumption (CPU, memory)
- Impact on target application performance
- Agent response time to alerts
- System stability with/without AI

**Expected Results**:

- Agent CPU usage: **<5%**
- Agent memory: **<150MB**
- Response time: **<2 seconds**
- Target app impact: **~0%**

**Duration**: ~5 minutes

**Read more**: [demo1-baseline/README.md](demo1-baseline/README.md)

---

### Demo 2: DDoS Attack Detection & Response

**Objective**: Demonstrate AI-powered attack detection and mitigation recommendations

**What it demonstrates**:

- Real-time traffic monitoring
- High request rate detection
- AI analysis of attack patterns
- Intelligent mitigation strategies

**Expected Results**:

- Attack detected: **<15 seconds**
- Agent response: **<5 seconds**
- Decision confidence: **>90%**
- System availability: **>90%** during attack

**Duration**: ~2 minutes

**Read more**: [demo2-ddos/README.md](demo2-ddos/README.md)

---

### Demo 3: CPU Stress Auto-Remediation

**Objective**: Showcase autonomous process management and auto-remediation

**What it demonstrates**:

- CPU monitoring and alerting
- Intelligent process identification
- Automatic process termination
- Multi-step workflow execution
- System recovery validation

**Expected Results**:

- Alert triggered: **<40 seconds**
- Process termination: **100% success**
- Agent confidence: **>95%**
- CPU recovery: **<30 seconds**

**Duration**: ~4 minutes

**Read more**: [demo3-cpu-stress/README.md](demo3-cpu-stress/README.md)

---

### Demo 4: Memory Exhaustion Auto-Remediation

**Objective**: Demonstrate AI-powered memory exhaustion detection and intelligent service restart

**What it demonstrates**:

- Real-time memory pressure monitoring
- Sustained memory usage pattern detection
- Intelligent service restart decisions
- Multi-step auto-remediation workflows
- Health verification post-recovery

**Expected Results**:

- Alert triggered: **<40 seconds**
- Service restart: **100% success**
- Agent confidence: **>85%**
- Memory recovery: **<30 seconds**

**Duration**: ~5 minutes

**Read more**: [demo4-memory/README.md](demo4-memory/README.md)

---

## 🚀 Quick Start Guide

### Prerequisites

Ensure the AIOps system is running:

```bash
# From project root
docker compose up -d --build

# Verify all services are running
docker compose ps

# Expected: 7 services running (target-app, prometheus, grafana, alertmanager, agent, etc.)
```

### Run Individual Demo

```bash
# Navigate to demo folder
cd demos/demo1-baseline

# Make scripts executable
chmod +x run.sh validate.sh

# Run the demo
./run.sh

# Validate results (after demo completes)
./validate.sh
```

### Run All Demos Sequentially

```bash
# From demos folder
chmod +x run-all-demos.sh
./run-all-demos.sh

# This will:
# 1. Run Demo 1 (Baseline)
# 2. Wait 30s
# 3. Run Demo 2 (DDoS)
# 4. Wait 30s
# 5. Run Demo 3 (CPU Stress)
# 6. Wait 30s
# 7. Run Demo 4 (Memory)
# 8. Generate combined report
```

**Note**: Running all demos sequentially takes approximately **20-25 minutes**. For faster evaluation, run individual demos from their respective folders.

---

## 📊 Understanding Results

### Results Files

Each demo generates timestamped results:

```
demos/demo1-baseline/results/baseline_20260324_143022.txt
demos/demo2-ddos/results/ddos_20260324_144130.txt
demos/demo3-cpu-stress/results/cpu_stress_20260324_145215.txt
```

### Results Structure

Every results file contains:

1. **Test Parameters**: Configuration and settings used
2. **Baseline Metrics**: Pre-test system state
3. **Attack/Stress Phase**: During-test measurements
4. **AI Agent Decisions**: LLM analysis and actions
5. **Recovery Metrics**: Post-test system state
6. **Summary**: Key findings and validation status

### Validation Output

```bash
./validate.sh results/demo_timestamp.txt

# Output example:
═══ Validation Summary ═══
Validation Score: 8/8 (100%)

✅ ALL VALIDATIONS PASSED!

✓ Demo executed completely
✓ AI Agent responded correctly
✓ System recovered successfully
✓ All metrics within acceptable ranges
```

---

## 📈 Visualizing in Grafana

### Access Grafana

```bash
# Open in browser
http://localhost:3000

# Login
Username: admin
Password: admin123
```

### Recommended Dashboards

1. **NT531 AIOps System Overview** (Main dashboard)
   - Real-time metrics for all services
   - CPU/Memory/Network usage
   - Alert timeline
   - Agent decision log

2. **Time Range Selection**
   - Click time picker (top-right)
   - Select "Last 30 minutes" or custom range
   - Align with demo execution time

3. **Key Panels to Watch**
   - **Request Rate**: Spike during DDoS demo
   - **CPU Usage**: Spike during CPU stress demo
   - **Agent Actions**: Decision log entries
   - **Alert Status**: Red bars when alerts fire

---

## 🔍 Demo Comparison Matrix

| Feature                | Demo 1       | Demo 2            | Demo 3           | Demo 4            |
| ---------------------- | ------------ | ----------------- | ---------------- | ----------------- |
| **AI Decision Making** | Basic        | Advanced          | Expert           | Expert            |
| **Auto-Remediation**   | ❌ Manual    | ⚠️ Recommendation | ✅ Automatic     | ✅ Automatic      |
| **Process Management** | ❌ None      | ❌ None           | ✅ Full          | ⚠️ Service Mgmt   |
| **Attack Simulation**  | ❌ None      | ✅ DDoS           | ✅ CPU Stress    | ✅ Memory Stress  |
| **System Impact**      | Low          | Medium            | High             | High              |
| **Complexity**         | Simple       | Medium            | Complex          | Complex           |
| **Duration**           | ~5 min       | ~2 min            | ~4 min           | ~5 min            |
| **Success Metric**     | Overhead <5% | Detection <15s    | Termination 100% | Recovery <30s     |

---

## 🎓 Learning Path

### Recommended Order

1. **Start with Demo 1** (Baseline)
   - Understand the system architecture
   - Learn resource monitoring
   - See agent's basic functionality
   - Establish performance baseline

2. **Progress to Demo 2** (DDoS)
   - Observe attack detection
   - Analyze AI decision-making
   - Study mitigation strategies
   - Learn alert workflows

3. **Complete with Demo 3** (CPU Stress)
   - Experience auto-remediation
   - Understand process management
   - Study multi-step workflows
   - See full system capabilities

4. **Advance with Demo 4** (Memory Exhaustion)
   - Learn resource management
   - Observe trend analysis
   - Understand service orchestration
   - Master complex remediation scenarios

### Skills Developed

By completing all demos, you will learn:

- ✅ **System Monitoring**: Prometheus, Grafana, AlertManager
- ✅ **Container Management**: Docker operations, process control, service restart
- ✅ **AI Integration**: LLM decision-making, tool usage, trend analysis
- ✅ **Incident Response**: Detection, analysis, remediation, verification
- ✅ **Performance Analysis**: Metrics collection, comparison, trend detection
- ✅ **Testing Methodologies**: Load testing, stress testing, memory testing, validation

---

## 🛠️ Common Commands

### System Health

```bash
# Check all services
docker compose ps

# View AI agent logs
docker logs aiops-agent --tail 50

# Check agent health
curl http://localhost:8080/health | jq

# View recent decisions
curl http://localhost:8080/logs?limit=10 | jq
```

### Metrics & Monitoring

```bash
# Query Prometheus
curl "http://localhost:9090/api/v1/query?query=up"

# Check active alerts
curl http://localhost:9093/api/v1/alerts | jq

# View target app metrics
curl http://localhost:5000/metrics
```

### Emergency Cleanup

```bash
# Stop all demos
docker exec target-app pkill -9 stress-ng
docker exec target-app pkill -9 stress

# Restart services
docker compose restart

# Clean results
rm -rf demo*/results/*
```

---

## 🐛 Troubleshooting

### Demo Won't Start

```bash
# Problem: "Docker Compose is not running"
# Solution:
docker compose up -d
sleep 10

# Problem: "AI Agent not accessible"
# Solution:
docker compose restart agent
curl http://localhost:8080/health
```

### Alert Not Triggering

```bash
# Check Prometheus is scraping
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, state: .health}'

# Verify alert rules
docker exec prometheus /bin/promtool check rules /etc/prometheus/alert.rules.yml

# Check AlertManager config
curl http://localhost:9093/api/v1/status | jq
```

### Agent Not Responding

```bash
# Check agent status
docker logs aiops-agent --tail 100

# Verify API key
docker exec aiops-agent env | grep GEMINI_API_KEY

# Test webhook manually
curl -X POST http://localhost:8080/webhook \
  -H 'Content-Type: application/json' \
  -d '{"alerts":[{"status":"firing","labels":{"alertname":"TestAlert"}}]}'
```

---

## 📚 Additional Resources

### Documentation

- [Main Project README](../README.md) - System overview & architecture
- [PROJECT_PLAN.md](../PROJECT_PLAN.md) - Development methodology
- [COMPREHENSIVE_TEST_REPORT.md](../COMPREHENSIVE_TEST_REPORT.md) - Full test results

### Monitoring Tools

- **Prometheus**: [http://localhost:9090](http://localhost:9090)
- **Grafana**: [http://localhost:3000](http://localhost:3000)
- **AlertManager**: [http://localhost:9093](http://localhost:9093)
- **AI Agent**: [http://localhost:8080](http://localhost:8080)

### API Endpoints

```bash
# Agent
GET  /health              # Health check
GET  /logs?limit=N        # Recent decisions
POST /webhook             # Alert receiver

# Target App
GET  /                    # Normal endpoint
GET  /health              # Health check
GET  /heavy               # CPU-intensive endpoint
GET  /metrics             # Prometheus metrics
```

---

## 🎯 Success Criteria

### Demo 1: Baseline Assessment

- ✅ Agent overhead <5% CPU, <150MB RAM
- ✅ Target app performance unchanged
- ✅ Agent responds to test alert
- ✅ System remains 100% stable

### Demo 2: DDoS Response

- ✅ Attack detected within 15 seconds
- ✅ Agent analyzes and recommends mitigation
- ✅ System maintains >90% availability
- ✅ Recovery after attack ends

### Demo 3: CPU Stress Auto-Remediation

- ✅ CPU spike detected (>80%)
- ✅ Agent identifies stress processes
- ✅ **100% process termination success**
- ✅ CPU returns to baseline <30s

### Demo 4: Memory Exhaustion Auto-Remediation

- ✅ Memory pressure detected (>80%)
- ✅ Agent identifies memory trend
- ✅ **Service restart execution 100% success**
- ✅ Memory returns to baseline <30s

---

## 📊 Performance Benchmarks

| Metric                       | Target | Typical | Excellent |
| ---------------------------- | ------ | ------- | --------- |
| **Detection Time**           | <30s   | ~15s    | <10s      |
| **Agent Response**           | <5s    | ~2s     | <1s       |
| **Decision Confidence**      | >80%   | ~90%    | >95%      |
| **Auto-Remediation Success** | >80%   | ~95%    | 100%      |
| **System Availability**      | >95%   | ~98%    | 100%      |
| **Agent Overhead**           | <10%   | ~5%     | <3%       |

---

## 💡 Tips for Best Results

1. **Run demos individually first** - Understand each before running all
2. **Monitor Grafana during execution** - Watch metrics in real-time
3. **Read agent logs** - Understand AI reasoning process
4. **Compare results** - Analyze delta between baseline and stress
5. **Validate every demo** - Use validation scripts
6. **Clean between runs** - Restart services for fresh state

---

## 🏆 Congratulations!

By completing these demos, you've successfully:

- ✅ Validated an AI-powered AIOps system
- ✅ Demonstrated autonomous incident response (4 scenarios)
- ✅ Measured system performance and overhead
- ✅ Verified auto-remediation capabilities (process kill + service restart)
- ✅ Gained hands-on experience with production tools
- ✅ Seen advanced AI decision-making in real scenarios

**These results demonstrate a system that exceeds NT531 course requirements and showcases production-ready AIOps capabilities!**

---

**Need help?**

- Check individual demo READMEs for detailed explanations
- Review troubleshooting sections above
- Examine agent logs: `curl http://localhost:8080/logs | jq`
- Monitor Grafana dashboards: `http://localhost:3000`

**Ready to present?**

- Run `./run-all-demos.sh` for comprehensive testing
- Export Grafana dashboards for visuals
- Save result files for evidence
- Take screenshots of key metrics

---

📖 **[Back to Project README](../README.md)**
