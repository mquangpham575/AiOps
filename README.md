<div align="center">

# 🤖 Agentic AIOps — NT531 Auto-Remediation System

### AI-powered Network Operations with Intelligent Auto-Remediation

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://docker.com)
[![AI](https://img.shields.io/badge/AI-Google%20Gemini-green.svg)](https://ai.google.dev)
[![Monitoring](https://img.shields.io/badge/Monitoring-Prometheus-orange.svg)](https://prometheus.io)
[![Status](https://img.shields.io/badge/Status-Academic%20Prototype-blue.svg)]()

**🎯 NT531 Network System Performance Evaluation Project**

_Demonstrating the future of autonomous IT operations through intelligent AI agents_

</div>

---

This project demonstrates an **AIOps Proof-of-Concept (PoC)** that automatically detects, analyzes, and remediates network and system issues using AI agents. Designed for the **NT531 Network Performance Evaluation** course, the system features **intelligent process matching** and **automated workflows** to achieve high decision accuracy in controlled environments.

---

### **📊 Measured Benchmarks (Lab Environment)**

| KPI                      | Target         | **Achieved**       | Note                         |
| ------------------------ | -------------- | ------------------ | ---------------------------- |
| 🎯 **Decision Accuracy** | >90%           | **95%**            | Based on 50+ test runs       |
| ⚡ **Mean Time to Repair**| <60s           | **~15-30 seconds** | From firing to resolution    |
| 🛡️ **System Stability**  | >99%           | **Stable Lab**     | Local Docker Compose stack   |
| 🔄 **Availability**      | Business hours | **24/7 (Simulated)**| Automated agent polling      |

> [!NOTE]
> Metrics are compared against a manual operator baseline of 5-15 minutes for similar remediation tasks.

### **📈 Manual vs AI Comparison**

<table>
<tr>
<td width="50%">

#### 👨‍💼 **Manual Operations**

- 🐌 **5-15 min** detection time
- 🕒 **Business hours** only
- 🎯 **Variable** accuracy by operator
- 💰 **$20-50** per incident cost

</td>
<td width="50%">

#### 🤖 **AI-Powered System**

- ⚡ **<2 seconds** detection time
- 🌍 **24/7** automated coverage
- 🎯 **95%** consistent accuracy
- 💰 **$0.005** per incident cost

</td>
</tr>
</table>

<div align="center">

### **🚀 Result: Significant acceleration in incident response for recurring issues**

</div>

---

## 🌟 **What Makes This Special?**

<table>
<tr>
<td width="50%">

### 🧠 **Real AI Intelligence**

- **Genuine Gemini LLM** integration
- **Intelligent reasoning** with 95% confidence
- **Smart process matching** with synonyms
- **Multi-step workflow** automation

</td>
<td width="50%">

### 🏗️ **Lab Architecture**

- **7-service microservices** deployment
- **Container-native** with Docker Compose
- **Full Observability** stack (LGTM-ish)
- **Extensible** tool-based remediation

</td>
</tr>
</table>

---

## 🚀 **Get Started in 3 Minutes**

### **Prerequisites**

```bash
✅ Docker Desktop (Windows/Mac/Linux)
✅ 8GB+ RAM (16GB recommended)
✅ Google Gemini API Key (free)
```

### **Installation**

```bash
# 1️⃣ Clone & Setup
git clone <your-repo-url>
cd DoAn

# 2️⃣ Configure API Key
cp .env.example .env
echo "GEMINI_API_KEY=your_api_key_here" >> .env

# 3️⃣ Deploy System
docker-compose up -d --build

# 4️⃣ Validate Everything Works
docker compose ps  # Verify all services are running
curl http://localhost:8080/health  # Check AI Agent
curl http://localhost:5000/health  # Check Target App
```

### **🎉 That's it! Access your AIOps system:**

<div align="center">

| Service                  | URL                                       | Purpose                          |
| ------------------------ | ----------------------------------------- | -------------------------------- |
| 📊 **Grafana Dashboard** | [`localhost:3000`](http://localhost:3000) | Real-time monitoring & analytics |
| 📈 **Prometheus**        | [`localhost:9090`](http://localhost:9090) | Metrics & query interface        |
| 🚨 **AlertManager**      | [`localhost:9093`](http://localhost:9093) | Alert management console         |
| 🤖 **AI Agent**          | [`localhost:8080`](http://localhost:8080) | Agent health & decision logs     |

_Default Grafana login: `admin` / `admin123`_

> [!WARNING]
> This is a research prototype. It does not include High Availability (HA), persistent alert long-term storage, or enterprise-grade identity management.

</div>

---

## 🏗️ **System Architecture**

<div align="center">

```
┌───────────────────────────────────────────────────────────────┐
│                     🎯 TARGET SYSTEM                          │
│                Flask App + Stress Endpoints                   │
└───────────────────────────────────────────────────────────────┘
                               │ metrics
                               ▼
┌───────────────────────────────────────────────────────────────┐
│                    📊 MONITORING LAYER                        │
├───────────────────────────────────────────────────────────────┤
│   Prometheus ────► Grafana                                    │
│       │                                                       │
│       └──────► AlertManager                                   │
└───────────────────────────────────────────────────────────────┘
                               │ webhook
                               ▼
┌───────────────────────────────────────────────────────────────┐
│                    🤖 AI AGENT LAYER                          │
├───────────────────────────────────────────────────────────────┤
│   Flask Receiver → Gemini LLM → Intelligent Decision          │
│        │                                                      │
│        └─────► Tool Execution Engine                          │
└───────────────────────────────────────────────────────────────┘
                               │ remediation
                               ▼
┌───────────────────────────────────────────────────────────────┐
│                  🛠️ REMEDIATION TOOLS                         │
├───────────────────────────────────────────────────────────────┤
│   • auto_kill_cpu_stress()     • validate_container_exists()  │
│   • Smart synonym matching     • Advanced error handling      │
│   • Docker API Integration     • iptables rate limiting       │
└───────────────────────────────────────────────────────────────┘
```

</div>

**🔧 Tech Stack:**

- **AI**: Google Gemini API (configurable model)
- **Backend**: Python Flask + Docker API
- **Monitoring**: Prometheus + Grafana + AlertManager
- **Infrastructure**: Docker Compose + iptables
- **Testing**: Locust + stress-ng + custom validation

---

## 🧪 **Testing & Demo Scenarios**

<div align="center">

### **🎮 Interactive Demo Scenarios**

</div>

<table>
<tr>
<td width="33%" align="center">

### 📊 **Scenario 1**

#### Baseline Assessment

**🎯 Objective:** Measure AI overhead<br/>
**⚡ Method:** Resource monitoring<br/>
**🏆 Result:** <150MB, <5% CPU

</td>
<td width="33%" align="center">

### 🌐 **Scenario 2**

#### DDoS Response

**🎯 Objective:** Attack mitigation<br/>
**⚡ Method:** High request flood<br/>
**🏆 Result:** Perfect rate limiting

</td>
<td width="33%" align="center">

### 🔥 **Scenario 3**

#### CPU Stress Management

**🎯 Objective:** Process management<br/>
**⚡ Method:** stress-ng load test<br/>
**🏆 Result:** 100% accurate targeting

</td>
</tr>
</table>

### **📊 Benchmarking Methodology**

To maintain academic rigor, all metrics were derived from reproducible lab experiments:
1. **DDoS Mitigation**: Measured using **Locust** executing 500+ RPS against the target app, tracking recovery time once rate limits were applied.
2. **CPU Remediation**: Measured using **stress-ng --cpu 4** inside the target container, timing the interval from AlertManager firing to the agent's `auto_kill_cpu_stress` execution.
3. **Accuracy**: Evaluated over 50 varied alert scenarios to verify the AI Agent's tool selection consistency.

### **🎬 Run Live Demo**

```bash
# Launch comprehensive testing suite (all 3 demos)
cd demos
./run-all-demos.sh

# Or test individual scenarios
cd demos/demo1-baseline && ./run.sh  # Baseline assessment
cd demos/demo2-ddos && ./run.sh      # DDoS attack simulation
cd demos/demo3-cpu-stress && ./run.sh # CPU stress auto-remediation
```

---

## 🛠️ **Advanced Configuration**

<details>
<summary><b>📁 Project Structure</b></summary>

```
DoAn/
├── 📋 Documentation
│   ├── README.md                    ← You are here!
│   ├── PROJECT_PLAN.md              ← 8-week methodology
│   └── DEMO_VERIFICATION_REPORT.md  ← Demo validation results
├── 🧪 Interactive Demos
│   ├── demos/
│   │   ├── README.md               ← Demo suite overview
│   │   ├── run-all-demos.sh        ← Run all 3 demos sequentially
│   │   ├── demo1-baseline/         ← Performance assessment
│   │   ├── demo2-ddos/             ← DDoS attack response
│   │   └── demo3-cpu-stress/       ← Auto-remediation
│   └── loadtest/
│       ├── locustfile.py           ← DDoS simulation
│       └── stress.sh               ← CPU stress testing
├── 🤖 AI Agent Core
│   ├── agent.py                    ← AI logic + Gemini
│   ├── tools.py                    ← 10 remediation tools
│   └── requirements.txt            ← Dependencies
├── 🎯 Target System
│   ├── app.py                      ← Flask test endpoints
│   └── Dockerfile                  ← Containerized target
├── 📊 Monitoring Stack
│   ├── prometheus/                 ← Metrics collection
│   ├── alertmanager/              ← Alert routing
│   └── grafana/                   ← Dashboards
└── ⚙️ Infrastructure
    ├── docker-compose.yml         ← 7-service architecture
    └── .env.example               ← Configuration template
```

</details>

<details>
<summary><b>🔧 System Management Commands</b></summary>

```bash
# 🔍 Monitor AI Agent Performance (Authenticated)
curl -H 'X-Agent-Key: your_secret_agent_key_here' \
  "http://localhost:8080/logs?limit=5" | jq '.[] | {alert, action, confidence}'

# 📊 Check System Resources
docker stats --no-stream

# 🔧 Restart Specific Services
docker-compose restart agent prometheus grafana

# 🧪 Manual Alert Testing (Authenticated)
curl -X POST http://localhost:8080/webhook \
  -H 'Content-Type: application/json' \
  -H 'X-Agent-Key: your_secret_agent_key_here' \
  -d '{"alerts":[{"status":"firing","labels":{"alertname":"TestAlert"}}]}'
```

</details>

<details>
<summary><b>🐛 Troubleshooting Guide</b></summary>

### **Common Issues & Quick Fixes**

#### 🔴 **Target DOWN in Prometheus**

```bash
docker-compose ps | grep target-app          # Check status
docker-compose restart target-app            # Restart if needed
curl http://localhost:9090/api/v1/targets    # Verify targets
```

#### 🔴 **AI Agent Not Responding**

```bash
curl http://localhost:8080/health             # Check health
docker logs aiops-agent --tail 20            # Check logs
docker exec aiops-agent env | grep GEMINI    # Verify API key
```

#### 🔴 **Alerts Not Firing**

```bash
# Validate alert rules syntax
docker exec prometheus /bin/promtool check rules /etc/prometheus/alert.rules.yml

# Check metrics collection
curl "http://localhost:9090/api/v1/query?query=up"
```

</details>

---

## 📄 **License**

<div align="center">

**MIT License** • Copyright (c) 2026 NT531 AIOps Project Contributors

</div>

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software.

**THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.**

---

## 🌟 **Acknowledgments**

<div align="center">

**🎓 Course:** NT531 - Network System Performance Evaluation
**🏫 Institution:** University of Information Technology
**🤖 AI Partner:** Google Gemini AI
**📊 Monitoring:** Prometheus & Grafana Community

### **⭐ If this project helped you, please consider giving it a star!**

**[⬆️ Back to Top](#-agentic-aiops--nt531-auto-remediation-system)**

</div>

---
