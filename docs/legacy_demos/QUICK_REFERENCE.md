# NT531 AIOps — Quick Reference (Current)

This repo no longer uses the legacy `demos/*/run.sh` + `validate.sh` scripts.
Those are archived; use the config-driven scenario runner instead.

## Start / Stop

- Preferred (starts Azure VMs, opens SSH tunnel for Docker, starts local control plane):
  - `powershell -ExecutionPolicy Bypass -File .\scripts\aiops-power.ps1 start`
- Stop:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\aiops-power.ps1 stop`

## Run scenarios

```bash
python scripts/demo_runner.py --scenario all
python scripts/demo_runner.py --scenario throughput
python scripts/demo_runner.py --scenario cpu
python scripts/demo_runner.py --scenario memory
```

AI vs Rule-based comparison (run twice, swap agent URL):

```bash
python scripts/demo_runner.py --scenario cpu --agent-url http://localhost:8080
python scripts/demo_runner.py --scenario cpu --agent-url http://localhost:5001
```

## Health checks (PC)

```bash
docker compose -f docker-compose.control.yml ps
curl http://localhost:9090/-/ready
curl http://localhost:8080/health
curl http://localhost:5001/health
```

## Dashboards

- Grafana runs on the loadgen VM: `http://$AZURE_LOADGEN_IP:3000`
- Prometheus (PC): `http://localhost:9090`
- AlertManager (PC): `http://localhost:9093`

## Output

- Scenario runner exports CSV (default `results.csv`) with per-iteration rows + `summary` rows.
- Scenario definitions are in `scenarios/config.yml`.

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

The legacy demo scripts were removed. If you want to clean archived logs, delete files under `demos/**/results/` manually.

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

Legacy demo scripts were removed. To clean archived logs, delete files under `demos/**/results/` manually.

### Force Remove Containers

```bash
docker compose down -v  # Removes volumes too
docker compose up -d --build  # Fresh start
```

---

## Grafana Dashboard Quick Access

1. Open `http://$AZURE_LOADGEN_IP:3000`
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
# START SYSTEM (preferred)
powershell -ExecutionPolicy Bypass -File .\scripts\aiops-power.ps1 start

# RUN SCENARIOS
python scripts/demo_runner.py --scenario all
python scripts/demo_runner.py --scenario throughput
python scripts/demo_runner.py --scenario cpu
python scripts/demo_runner.py --scenario memory

# HEALTH CHECKS
curl http://localhost:8080/health | jq  # Agent
curl http://localhost:8080/logs | jq   # Decisions
docker compose -f docker-compose.control.yml ps

# MONITORING
http://$AZURE_LOADGEN_IP:3000            # Grafana (loadgen VM)
http://localhost:9090                    # Prometheus (PC)
http://localhost:9093                    # AlertManager (PC)

# CLEANUP
docker exec target-app pkill -9 stress-ng  # Kill stress
docker compose restart                      # Restart all
```

---

**Need more details?** Use the current docs:

- `DEMO_GUIDE.md`
- `scenarios/README.md`
- `demos/README.md` (archived results overview)
