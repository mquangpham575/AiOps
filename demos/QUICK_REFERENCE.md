# NT531 AIOps Demos - Quick Reference

**Purpose:** Run and validate 3 AIOps demonstrations
**Time Required:** ~15 minutes for all demos
**Last Updated:** 2026-03-24

---

## Prerequisites & System Startup

### Start All Services

```bash
cd d:/Study/3rd-y/3rdY-Sem2/NT531.Q21-DanhGiaHieuNang/DoAn
docker compose up -d --build
```

### Verify System Health

```bash
# Check all 7 services are running
docker compose ps

# Quick health checks
curl http://localhost:8080/health  # AI Agent
curl http://localhost:5000/health  # Target App
curl http://localhost:9090/-/healthy  # Prometheus
```

**Expected:** All services show status "Up"

---

## Demo Quick Reference

| Demo       | Purpose              | Run Command                             | Duration | Validation      | Success Criteria                                    |
| ---------- | -------------------- | --------------------------------------- | -------- | --------------- | --------------------------------------------------- |
| **Demo 1** | Baseline Performance | `cd demos/demo1-baseline && ./run.sh`   | ~5 min   | `./validate.sh` | Agent CPU <5%, Memory <150MB, Response <2s          |
| **Demo 2** | DDoS Response        | `cd demos/demo2-ddos && ./run.sh`       | ~2 min   | `./validate.sh` | Detection <15s, Agent response <5s, Confidence >90% |
| **Demo 3** | CPU Auto-Remediation | `cd demos/demo3-cpu-stress && ./run.sh` | ~4 min   | `./validate.sh` | CPU spike >80%, 100% process kill, Recovery <30s    |

### Run All Demos Sequentially

```bash
cd demos
./run-all-demos.sh
```

**Duration:** ~15 minutes (includes cooldown periods)
**Output:** Combined report in `demos/combined_results/`

---

## Service URLs & Access

| Service               | URL                   | Credentials    | Health Check  |
| --------------------- | --------------------- | -------------- | ------------- |
| **Grafana Dashboard** | http://localhost:3000 | admin/admin123 | `/api/health` |
| **Prometheus**        | http://localhost:9090 | -              | `/-/healthy`  |
| **AlertManager**      | http://localhost:9093 | -              | `/-/healthy`  |
| **Target App**        | http://localhost:5000 | -              | `/health`     |
| **AI Agent**          | http://localhost:8080 | -              | `/health`     |

### Key API Endpoints

```bash
# View agent decisions
curl http://localhost:8080/logs?limit=10 | jq

# Check active alerts
curl http://localhost:9093/api/v2/alerts | jq

# Query Prometheus metrics
curl "http://localhost:9090/api/v1/query?query=up"
```

---

## Validation Score Guide

### Score Interpretation

- **100% (X/X)** = All checks passed ✅
- **60-99%** = Partial success, review failures ⚠️
- **<60%** = Failed, needs investigation ❌

### Validation Checks by Demo

- **Demo 1:** 5/5 checks (file integrity, metrics, agent function, health)
- **Demo 2:** 7/7 checks (attack execution, alert trigger, agent response, recovery)
- **Demo 3:** 8/8 checks (stress creation, detection, remediation, recovery, cleanup)

### Expected Output

```bash
./validate.sh

# Success example:
Validation Score: 8/8 (100%)
✅ EXCELLENT - AUTO-REMEDIATION SUCCESSFUL!
✓ All required sections present
✓ Agent detected and responded to alerts
✓ System recovered to normal state
```

---

## Results Files Location

Each demo generates timestamped results:

```
demos/demo1-baseline/results/baseline_YYYYMMDD_HHMMSS.txt
demos/demo2-ddos/results/ddos_YYYYMMDD_HHMMSS.txt
demos/demo3-cpu-stress/results/cpu_stress_YYYYMMDD_HHMMSS.txt
demos/combined_results/full_demo_report_YYYYMMDD_HHMMSS.txt
```

---

## Quick Troubleshooting

### Issue: Services not running

```bash
docker compose ps  # Check status
docker compose up -d  # Start services
```

### Issue: Alert not triggering

```bash
# Check AlertManager
curl http://localhost:9093/api/v2/alerts | jq

# Verify Prometheus targets
curl http://localhost:9090/api/v1/targets | jq
```

### Issue: Agent not responding

```bash
# Check agent logs
docker logs aiops-agent --tail 50

# Verify API key
docker exec aiops-agent env | grep GEMINI_API_KEY

# Restart agent
docker compose restart agent
```

### Issue: Demo stuck/hanging

```bash
# Kill stress processes
docker exec target-app pkill -9 stress-ng
docker exec target-app pkill -9 stress

# Restart all
docker compose restart
```

### Issue: Old results cluttering

```bash
# Clean individual demo
cd demos/demo1-baseline && ./run.sh --clean

# Clean all demos
cd demos && ./run-all-demos.sh --clean
```

---

## Emergency Commands

### Stop Everything

```bash
docker compose down
```

### Restart All Services

```bash
docker compose restart
```

### View Service Logs

```bash
docker logs aiops-agent --tail 100
docker logs target-app --tail 100
docker logs prometheus --tail 100
```

### Clean All Results

```bash
cd demos
./run-all-demos.sh --clean
```

### Force Remove Containers

```bash
docker compose down -v  # Removes volumes too
docker compose up -d --build  # Fresh start
```

---

## Grafana Dashboard Quick Access

1. Open http://localhost:3000
2. Login: **admin** / **admin123**
3. Select dashboard: **"NT531 AIOps System Overview"**
4. Set time range: **Last 30 minutes**

### Key Panels to Watch

- **CPU Usage** - Monitor spikes during demos
- **Request Rate** - DDoS attack visualization
- **Agent Actions** - AI decision log
- **Alert Status** - Red bars when alerts fire

---

## Performance Metrics Summary

| Metric                  | Target | Typical Achievement |
| ----------------------- | ------ | ------------------- |
| **Agent CPU**           | <5%    | ~2-3%               |
| **Agent Memory**        | <150MB | ~60-120MB           |
| **Response Time**       | <5s    | <2s                 |
| **Detection Time**      | <40s   | ~15-35s             |
| **Decision Confidence** | >90%   | 95-98%              |
| **System Uptime**       | >99%   | 100%                |

---

## Command Reference Card

```bash
# START SYSTEM
docker compose up -d --build

# RUN ALL DEMOS
cd demos && ./run-all-demos.sh

# RUN INDIVIDUAL DEMO
cd demos/demo1-baseline && ./run.sh && ./validate.sh
cd demos/demo2-ddos && ./run.sh && ./validate.sh
cd demos/demo3-cpu-stress && ./run.sh && ./validate.sh

# HEALTH CHECKS
curl http://localhost:8080/health | jq  # Agent
curl http://localhost:8080/logs | jq   # Decisions
docker compose ps                        # All services

# MONITORING
open http://localhost:3000               # Grafana
open http://localhost:9090               # Prometheus
open http://localhost:9093               # AlertManager

# CLEANUP
docker exec target-app pkill -9 stress-ng  # Kill stress
docker compose restart                      # Restart all
./run.sh --clean                            # Clean results
```

---

**Need more details?** See individual demo READMEs:

- `demos/demo1-baseline/README.md`
- `demos/demo2-ddos/README.md`
- `demos/demo3-cpu-stress/README.md`
- `demos/README.md` (overview)
