# Demo Guide — AIOps 3-Node Azure Cluster

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [System Startup](#system-startup)
3. [Running Evaluation Scenarios](#running-evaluation-scenarios)
4. [Output & Results](#output--results)
5. [Troubleshooting](#troubleshooting)

---

## Prerequisites

1. **Azure subscription** with access to resource group `rg-aiops`
2. **SSH key**: `.ssh/aiops3_key_rsa` in project root
3. **Azure CLI**: Logged in (`az login`)
4. **Python 3.10+**

---

## System Startup

### Step 1: Deploy Infrastructure

```powershell
# Start all 3 VMs and deploy containers
.\scripts\aiops-power.ps1 start
```

This will:
1. Start 3 Azure VMs (Control, LoadGen, App)
2. Clone/pull the repo on each VM
3. Deploy Docker containers via docker-compose

### Step 2: Access Dashboards

> **Note:** Public IPs are ephemeral. Run `.\scripts\aiops-power.ps1 status` to get current IPs.

| Service | Node | Private IP | Default Port |
|---------|------|-----------|-------------|
| Grafana | Control (Node 1) | 10.0.1.4 | 3000 |
| AI Agent Logs | Control (Node 1) | 10.0.1.4 | 8083/logs/ui |
| Prometheus | Control (Node 1) | 10.0.1.4 | 9090 |
| Pushgateway | Control (Node 1) | 10.0.1.4 | 9091 |
| Target App | App (Node 3) | 10.0.1.6 | 80/health |
| cAdvisor | App (Node 3) | 10.0.1.6 | 8080 |

Grafana dashboards are auto-provisioned from `ops/monitoring/grafana/dashboards/`:
- `aiops_pro_v1.json` — Cluster Observability (golden signals, infra health)
- `agent-analytics.json` — Agent Insights (throughput, decision metrics)
- `mttr-comparison.json` — MTTR Comparison: AI vs Rule-Based

### Step 3: Verify Status

```powershell
.\scripts\aiops-power.ps1 status
```

---

## Running Evaluation Scenarios

Scenarios must be run from **Node 2 (LoadGen)** for accurate load injection and metric collection.

### Option 1: Azure RunCommand (Recommended)

```powershell
# Throughput scenario (60s)
az vm run-command invoke -g rg-aiops -n aiops-loadgen-vm `
  --command-id RunShellScript `
  --scripts "cd /home/azureuser/3rdY-Sem2 && python3 scripts/demo_runner.py --scenario throughput --iterations 1 --duration 60 --target-url http://10.0.1.6:80 --agent-url http://10.0.1.4:8083 --prometheus-url http://10.0.1.4:9090"

# CPU MTTR scenario
az vm run-command invoke -g rg-aiops -n aiops-loadgen-vm `
  --command-id RunShellScript `
  --scripts "cd /home/azureuser/3rdY-Sem2 && python3 scripts/demo_runner.py --scenario cpu --iterations 1 --duration 60 --target-url http://10.0.1.6:80 --agent-url http://10.0.1.4:8083 --prometheus-url http://10.0.1.4:9090"
```

### Option 2: Direct SSH

```bash
# SSH into Node 2
ssh -i .ssh/aiops3_key_rsa azureuser@<LOADGEN_PUBLIC_IP>

# Run all scenarios
cd /home/azureuser/3rdY-Sem2
python3 scripts/demo_runner.py --scenario all --iterations 1 \
  --target-url http://10.0.1.6:80 \
  --agent-url http://10.0.1.4:8083 \
  --prometheus-url http://10.0.1.4:9090
```

### Custom Parameters

```bash
python scripts/demo_runner.py --scenario throughput --iterations 3 --duration 300 --json-output
```

---

## Output & Results

### Directory Structure

```
results/
├── all_scenarios.json           # Combined JSON
├── throughput/
│   ├── runs/
│   │   ├── run_001/
│   │   │   ├── baseline_metrics.json
│   │   │   └── load_metrics.json
│   │   └── run_002/
│   ├── summary.json             # Aggregated stats (mean +/- stdev)
│   ├── comparison.json          # Baseline vs Load comparison
│   └── results.csv
├── cpu/
│   └── ...
└── memory/
    └── ...
```

### Quick View

```bash
cat results/throughput/comparison.json | jq
cat results/cpu/summary.json | jq
```

---

## Baseline Comparison

| Scenario | Baseline | Load/Stress | Pass Criteria |
|----------|----------|-------------|---------------|
| throughput | 20 users, stable | 50-500 users, staged | Load p95 < 3x Baseline p95 |
| cpu | Normal | stress-ng injection | MTTR < threshold |
| memory | Normal | Legitimate + Attack | Success rate > threshold |

---

## Shutdown

```powershell
.\scripts\aiops-power.ps1 stop
```

---

## Troubleshooting

### "SSH Permission Denied"
- Verify SSH key exists: `.ssh/aiops3_key_rsa`
- Verify VM is running: `.\scripts\aiops-power.ps1 status`

### "Metrics are empty"
- Wait 30-60s after startup for Prometheus to begin scraping
- Check targets: `http://<CONTROL_PUBLIC_IP>:9090/targets`

### Check Running Containers

```bash
ssh -i .ssh/aiops3_key_rsa azureuser@<CONTROL_PUBLIC_IP> "docker ps"
```

---

## Demo Tips

1. **Run 1 iteration first** to verify setup:
   ```bash
   python scripts/demo_runner.py --scenario throughput --iterations 1 --json-output
   ```

2. **Watch dashboards live** — open Grafana on `<CONTROL_PUBLIC_IP>:3000` during scenario execution

3. **Debug containers**:
   ```bash
   ssh -i .ssh/aiops3_key_rsa azureuser@<CONTROL_PUBLIC_IP>
   docker compose -f ops/infra/docker-compose.control.yml logs -f
   ```
