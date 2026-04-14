<div align="center">

# Agentic AIOps: NT531 Performance Evaluation System

### Automated Network Operations through Intelligent AI Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-gray.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://docker.com)
[![AI](https://img.shields.io/badge/AI-Google%20Gemini-4285F4.svg)](https://ai.google.dev)
[![Monitoring](https://img.shields.io/badge/Monitoring-Prometheus-E6522C.svg)](https://prometheus.io)
[![Status](https://img.shields.io/badge/Status-Academic%20Prototype-0078D4.svg)]()

**NT531 Network System Performance Evaluation Project**

</div>

---

## Project Overview

This repository contains a **Distributed AIOps Proof-of-Concept (PoC)** designed to automate the detection, analysis, and remediation of system incidents. The system evaluates the performance of an **LLM-powered AI Agent** in terms of **Time To Recovery (TTR)** and its impact on legitimate traffic so as to prove its value over traditional baselines.

The infrastructure is distributed across local and remote (Azure) environments:
- **Control Plane (Windows PC):** Runs Prometheus, AlertManager, and the AIOps Agents.
- **Observability Plane (Azure VM 1):** Runs Grafana dashboards.
- **Application Plane (Azure VM 2):** Runs the target application and metrics exporters.

---

## 📂 Repository Structure

```text
DoAn/
├── src/                           # ── SOURCE CODE ──
│   ├── agent/                     # AI and Rule-based Agents
│   └── app/                       # Target Flask Application
├── ops/                           # ── OPERATIONS & INFRA ──
│   ├── infra/                     # Docker Compose and Terraform
│   └── monitoring/                # Prometheus, AlertManager, Grafana
├── tests/                         # ── TESTING & BENCHMARKS ──
│   ├── performance/               # Locust files and Scenarios (Sc1, Sc3)
│   └── unit/                      # Pytest unit tests
├── scripts/                       # ── AUTOMATION SCRIPTS ──
│   ├── run_scenario1.sh           # Baseline vs Load Analysis
│   ├── run_scenario2.sh           # Manual vs AI TTR Analysis
│   ├── run_scenario3.sh           # DDoS Trade-off Analysis
│   └── aiops-power.ps1            # Full system power cluster control
├── docs/                          # Documentation and Legacy Demos
├── results/                       # CSV and Log outputs per scenario
└── DEMO_GUIDE.md                  # Quick-start instructions
```

---

## 🎯 Evaluation Scenarios

The system is evaluated through three primary performance scenarios:

1.  **Scenario 1: Baseline vs Load**: Measures system degradation (p95 latency) under idle vs. sustained load to identify resource breaking points.
2.  **Scenario 2: CPU Stress Auto-Remediation**: Quantifies the value of AI by comparing Manual Time-To-Remediation (TTR) against automated AI response.
3.  **Scenario 3: DDoS Mitigation Trade-off**: Evaluates the effectiveness of `iptables` rate limiting in blocking floods while measuring collateral damage to legitimate users.

---

## 🕹️ Getting Started

### 1. Power Control
The easiest way to manage the entire distributed system is via the PowerShell control script:

```powershell
# Start all VMs and containers (Local & Remote)
.\scripts\aiops-power.ps1 start

# Check status of the cluster
.\scripts\aiops-power.ps1 status
```

### 2. Manual Commands
If you need to run specific components:

```bash
# Start Control Plane locally
docker compose -f ops/infra/docker-compose.control.yml up -d --build
```

---

## 📊 Monitoring & Dashboards

Access the following interfaces once the system is running:

| Interface         | Address                         | Purpose                                        |
| :---------------- | :------------------------------ | :--------------------------------------------- |
| **Grafana**       | `http://<AZURE_IP>:3000`        | View Performance Dashboards (Import Sc JSON)  |
| **AI Action Log** | `http://localhost:8080/logs/ui` | Live view of AI reasoning and actions          |
| **Prometheus**    | `http://localhost:9090`         | Inspect metric scrape targets                  |

Import the tailored dashboard from: `ops/monitoring/grafana/dashboards/aiops_perf_eval.json`.

---

## 📈 Benchmarking

To run the full evaluation suite and generate reports:

```bash
./scripts/run_scenario1.sh  # Iterative Baseline Analysis
./scripts/run_scenario2.sh  # TTR Comparison
./scripts/run_scenario3.sh  # DDoS Mitigation Analysis
```

---

## 🌟 Acknowledgments

**🎓 Course:** NT531 - Network System Performance Evaluation
**🏫 Institution:** University of Information Technology
**🤖 AI Partner:** Google Gemini AI
