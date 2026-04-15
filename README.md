<div align="center">

# Agentic AIOps: NT531 Performance Evaluation System

### Automated Network Operations through Intelligent AI Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-gray.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://docker.com)
[![AI](https://img.shields.io/badge/AI-Google%20Gemini-4285F4.svg)](https://ai.google.dev)
[![Monitoring](https://img.shields.io/badge/Monitoring-Prometheus-E6522C.svg)](https://prometheus.io)
[![Load Testing](https://img.shields.io/badge/Load%20Testing-Locust-3DDC84.svg)](https://locust.io)
[![Status](https://img.shields.io/badge/Status-Academic%20Prototype-0078D4.svg)]()

**NT531 Network System Performance Evaluation Project**

</div>

---

## Project Overview

This repository contains a **Distributed AIOps Proof-of-Concept (PoC)** designed to automate the detection, analysis, and remediation of system incidents. The system evaluates the performance of an **LLM-powered AI Agent** in terms of **Time To Recovery (TTR)** and its impact on legitimate traffic so as to prove its value over traditional baselines.

The infrastructure is distributed across three Azure VMs (VNet: 10.0.1.0/24):
- **Node 1: Control Plane (aiops-control):** Runs Prometheus, AI Agent (Port 8083), and Rule-based Agent.
- **Node 2: Load Plane (aiops-loadgen):** Runs Locust load generator and Pushgateway.
- **Node 3: App Plane (aiops-app):** Runs the target Flask application and metrics exporters.

---

## 📂 Repository Structure

```text
DoAn/
├── src/                           # ── SOURCE CODE ──
│   ├── agent/                     # AI Agent + Rule-based Agent
│   │   ├── ai-agent/             # LLM-powered agent (Gemini)
│   │   └── rule-based-agent/     # Deterministic baseline agent
│   └── app/                      # Target Flask Application
├── ops/                           # ── OPERATIONS & INFRA ──
│   ├── infra/                     # Docker Compose configs
│   └── monitoring/                # Prometheus, AlertManager, Grafana
├── tests/                         # ── TESTING & BENCHMARKS ──
│   ├── performance/               # Locust load test files
│   │   ├── locustfile.py         # Unified load test (all scenarios)
│   │   └── scenarios.yml         # Scenario configuration
│   └── unit/                      # Pytest unit tests
├── scripts/                       # ── AUTOMATION SCRIPTS ──
│   ├── demo_runner.py            # Config-driven scenario runner (JSON output)
│   ├── run_all.sh               # Run all scenarios sequentially
│   ├── run_scenario1.sh         # Throughput & Latency
│   ├── run_scenario2.sh         # CPU Stress MTTR
│   ├── run_scenario3.sh         # Memory/DDoS Trade-off
│   └── aiops-power.ps1          # Azure VM power control
├── docs/                          # Documentation
├── results/                       # CSV and JSON outputs per scenario
└── DEMO_GUIDE.md                  # Quick-start instructions
```

---

## 🎯 Evaluation Scenarios

The system is evaluated through three primary performance scenarios:

| Scenario | Description | Key Metrics |
|----------|-------------|-------------|
| **1: Throughput** | Baseline vs Load comparison | p50/p95/p99 latency, RPS, error rate |
| **2: CPU MTTR** | AI vs Rule-Based Agent comparison | MTTR, detection time, response time |
| **3: Memory/DDoS** | Rate limiting trade-off | Success rate, block rate |

---

## 🕹️ Quick Start

### 1. Power Control
```powershell
# Start all VMs and containers
.\scripts\aiops-power.ps1 start

# Check status
.\scripts\aiops-power.ps1 status
```

### 2. Run Scenarios

```bash
# Run all scenarios (recommended)
./scripts/run_all.sh

# Run individual scenarios
./scripts/run_scenario1.sh    # Throughput baseline vs load
./scripts/run_scenario2.sh    # CPU MTTR comparison
./scripts/run_scenario3.sh    # Memory/DDoS trade-off

# Or use Python directly with JSON output
python scripts/demo_runner.py --scenario all --json-output
```

### 3. View Results

```bash
# JSON summary files
cat results/throughput/summary.json
cat results/throughput/comparison.json

# CSV export
cat results/throughput/results.csv
```

---

## 📊 Monitoring & Dashboards

Access the following interfaces once the system is running:

| Interface         | Address                         | Purpose                                        |
| :---------------- | :------------------------------ | :--------------------------------------------- |
| **Grafana**       | `http://104.215.191.69:3000`    | View Performance Dashboards                   |
| **AI Action Log** | `http://104.215.158.157:8083/logs/ui` | Live view of AI reasoning and actions         |
| **Prometheus**    | `http://104.215.158.157:9090`   | Inspect metric scrape targets                  |
| **Target App**    | `http://4.194.57.3:80`          | Target for performance testing                 |

Import dashboard: `ops/monitoring/grafana/dashboards/aiops_perf_eval.json`

---

## 📈 Output Format

Each scenario generates:

```
results/{scenario}/
├── runs/
│   ├── run_001/
│   │   └── {phase}_metrics.json     # Per-run metrics
│   └── run_002/
├── summary.json                      # Aggregated stats (mean ± stdev)
├── comparison.json                   # Baseline vs Load comparison
└── results.csv                       # CSV export
```

---

## 🌟 Acknowledgments

**🎓 Course:** NT531 - Network System Performance Evaluation
**🏫 Institution:** University of Information Technology
**🤖 AI Partner:** Google Gemini AI
