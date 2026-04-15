# AIOps 3-Node Azure Topology

## Overview

All infrastructure runs on Azure VMs — no local PC required for deployment.

```
┌─ Azure: rg-aiops  |  Region: Southeast Asia ─────────────────────────────────┐
│                                                                             │
│  VNet: aiops-vnet 10.0.0.0/16  |  Subnet: aiops-subnet 10.0.1.0/24        │
│                                                                             │
│  ┌─ Node 1: Control (aiops-control) ─────────────────────────────────────┐  │
│  │  VM: Standard_B2ps_v2  |  Private IP: 10.0.1.4                       │  │
│  │                                                                       │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐              │  │
│  │  │ Prometheus   │  │ AlertManager │  │ Grafana       │              │  │
│  │  │ :9090        │  │ :9093        │  │ :3000         │              │  │
│  │  └──────┬───────┘  └──────┬───────┘  └───────────────┘              │  │
│  │         │                 │                                          │  │
│  │    eval rules        webhook                                          │  │
│  │         │                 │                                          │  │
│  │         │       ┌─────────┴─────────┐                                │  │
│  │         │       │    AI Agent       │                                │  │
│  │         │       │    :8080         │                                │  │
│  │         │       └─────────┬─────────┘                                │  │
│  │         │                 │                                          │  │
│  │         │       ┌─────────┴─────────┐                                │  │
│  │         │       │ Rule-Based Agent  │                                │  │
│  │         │       │    :5001          │                                │  │
│  │         │       └───────────────────┘                                │  │
│  │                                                                       │  │
│  │  ┌──────────────┐                                                   │  │
│  │  │ Pushgateway  │                                                   │  │
│  │  │ :9091        │  (Receives Locust metrics)                         │  │
│  │  └──────────────┘                                                   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                              │                                              │
│                     scrape via VNet                                        │
│                              │                                              │
│  ┌─ Node 2: Load Gen (aiops-loadgen) ───────────────────────────────────┐  │
│  │  VM: Standard_D2ps_v5  |  Private IP: 10.0.1.5                       │  │
│  │                                                                       │  │
│  │  ┌──────────────┐  ┌──────────────┐                                 │  │
│  │  │ node-exporter│  │ Pushgateway  │                                 │  │
│  │  │ :9100        │  │ :9091        │  ← Locust pushes here            │  │
│  │  └──────────────┘  └──────────────┘                                 │  │
│  │                                                                       │  │
│  │  ┌──────────────────────────────────────────────────────────────┐    │  │
│  │  │ Locust (bare host, not containerized for max performance)   │    │  │
│  │  │                                                               │    │  │
│  │  │  locust -f tests/performance/locustfile.py \                 │    │  │
│  │  │    --host=http://10.0.1.6:80 --run-time 300s --headless      │    │  │
│  │  └──────────────────────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                              │                                              │
│                     HTTP traffic                                            │
│                              │                                              │
│  ┌─ Node 3: App (aiops-app) ────────────────────────────────────────────┐  │
│  │  VM: Standard_D2ps_v5  |  Private IP: 10.0.1.6                        │  │
│  │                                                                       │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐              │  │
│  │  │ target-app   │  │ node-exporter│  │ cAdvisor      │              │  │
│  │  │ :80 (Flask)  │  │ :9100        │  │ :8080         │              │  │
│  │  └──────────────┘  └──────────────┘  └───────────────┘              │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Node Summary

| Node | Name | VM Size | Private IP | Services |
|------|------|---------|------------|----------|
| 1 | aiops-control | B2ps_v2 | 10.0.1.4 | Prometheus, AlertManager, Grafana, AI Agent, Rule-Based Agent, Pushgateway |
| 2 | aiops-loadgen | D2ps_v5 | 10.0.1.5 | Locust (host), node-exporter, Pushgateway client |
| 3 | aiops-app | D2ps_v5 | 10.0.1.6 | target-app, node-exporter, cAdvisor |

---

## Network Flows

### Prometheus Scrape (Control → All Nodes)

```
Prometheus (10.0.1.4:9090) ──scrape──▶ 10.0.1.5:9100 (node-exporter-loadgen)
Prometheus (10.0.1.4:9090) ──scrape──▶ 10.0.1.5:9091 (pushgateway)
Prometheus (10.0.1.4:9090) ──scrape──▶ 10.0.1.6:80/metrics (target-app)
Prometheus (10.0.1.4:9090) ──scrape──▶ 10.0.1.6:9100 (node-exporter-app)
Prometheus (10.0.1.4:9090) ──scrape──▶ 10.0.1.6:8080 (cadvisor)
```

### Load Testing

```
Locust (10.0.1.5) ──HTTP──▶ target-app (10.0.1.6:80)  ~0.5ms RTT (VNet internal)
Locust ──push──▶ Pushgateway (10.0.1.5:9091) ──scrape──▶ Prometheus (10.0.1.4)
```

### Remediation

```
AlertManager (10.0.1.4) ──webhook──▶ AI Agent (10.0.1.4:8080)
AlertManager (10.0.1.4) ──webhook──▶ Rule-Based Agent (10.0.1.4:5001)
AI Agent ──Docker──▶ target-app (10.0.1.6)  (via SSH tunnel)
```

---

## SSH Access

All nodes accessible via SSH with the same key:

```bash
ssh -i .ssh/aiops3_key azureuser@10.0.1.4  # Control
ssh -i .ssh/aiops3_key azureuser@10.0.1.5  # Load Gen
ssh -i .ssh/aiops3_key azureuser@10.0.1.6  # App
```

---

## Deployment

Deploy all nodes:

```powershell
.\scripts\aiops-power.ps1 start
```

Check status:

```powershell
.\scripts\aiops-power.ps1 status
```

Stop all nodes:

```powershell
.\scripts\aiops-power.ps1 stop
```

---

## Access URLs

| Service | URL |
|---------|-----|
| Grafana | http://10.0.1.4:3000 |
| Prometheus | http://10.0.1.4:9090 |
| AlertManager | http://10.0.1.4:9093 |
| Pushgateway | http://10.0.1.5:9091 |
| Target App | http://10.0.1.6:80 |
| cAdvisor | http://10.0.1.6:8080 |
