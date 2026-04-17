<div align="center">

# Agentic AIOps: NT531 Performance Evaluation System

### Automated Network Operations through Intelligent AI Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-gray.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://docker.com)
[![AI](https://img.shields.io/badge/AI-Google%20Gemini-4285F4.svg)](https://ai.google.dev)
[![Monitoring](https://img.shields.io/badge/Monitoring-Prometheus-E6522C.svg)](https://prometheus.io)
[![Status](https://img.shields.io/badge/Status-Project%20Finalized-0078D4.svg)]()

**NT531 Network System Performance Evaluation Project**

</div>

---

## 🏗 Detailed Project Topology

The system is deployed across a stabilized **3-Node Azure Infrastructure** (VNet: `10.0.1.0/24`). All inter-node communication is secured via internal SSH and optimized for sub-second metric scraping.

| Node | Role | Public IP | Private IP | Key Components |
| :--- | :--- | :--- | :--- | :--- |
| **Node 1** | **Control Plane** | `104.215.158.157` | `10.0.1.4` | Prometheus, AI Agent, Rule Agent, Grafana |
| **Node 2** | **Load Generator** | `104.215.191.69` | `10.0.1.5` | Locust, DDoS Engine, Pushgateway |
| **Node 3** | **App Plane** | `4.194.57.3` | `10.0.1.6` | Target Flask App, Node Exporter, cAdvisor |

---

## 🧠 Autonomous Remediation Pipeline

The system evaluates an **LLM-powered AI Agent** (Gemini) that bridges the gap between observability and action.

1.  **Observability Layer**: Prometheus scrapes application and container metrics every 15s.
2.  **Alerting Layer**: AlertManager triggers webhooks to the AI Agent when thresholds (CPU > 70%, RAM > 80%, RPS > 60) are breached.
3.  **Reasoning Layer**: The AI Agent performs real-time metric analysis to identify the specific root cause (e.g., distinguishing between a legitimate traffic spike and a containerized CPU flood).
4.  **Action Layer**: The Agent executes autonomous tools via the `tools.py` toolbelt, including **Aggressive Process Killing** and **Service Recovery**.

---

## 🎯 Master Validation Scenarios (Remediation IQ)

The pipeline is field-proven across three definitive failure signatures:

### 🚨 Scenario 01: Intelligent CPU Flood Mitigation
- **Incident**: Distributed `stress-ng` core saturation.
- **AI Tool**: `auto_kill_cpu_stress` (High-Precision Kill).
- **Outcome**: Agent identifies the specific stress process and terminates it without impacting the parent app service.

### 🚨 Scenario 02: Memory Exhaustion Recovery
- **Incident**: Recursive memory leak causing OOM and latency degradation.
- **AI Tool**: `restart_service` (Clean State Restore).
- **Outcome**: Agent observes the RAM/Latency correlation and performs a soft-reset of the target container.

### 🚨 Scenario 03: DDoS Resilience & Recovery
- **Incident**: Brute-force parallel flood (60+ RPS).
- **AI Tool**: `restart_service` + connection clearing.
- **Outcome**: Agent monitors normalization and ensures the app recovers its baseline baseline ($<1\%$) as soon as the attack ceases.

---

## 📊 Monitoring & Performance Evidence

All metrics are synchronized to a **1-minute real-time window** across the following dashboards:

| Dashboard | Access URL | Purpose |
| :--- | :--- | :--- |
| **Cluster Observability** | [http://104.215.158.157:3000](http://104.215.158.157:3000) | Full system health & signals |
| **Agent Insights** | [http://104.215.158.157:3000](http://104.215.158.157:3000) | Live AI reasoning & MTTR traces |
| **MTTR Comparison** | [http://104.215.158.157:3000](http://104.215.158.157:3000) | AI vs Rule-Based performance audit |

---

## 🕹 Orchestration & Testing

For detailed instructions on triggering these scenarios and witnessing the Agent in action, refer to:
- **[demo-guide.md](file:///d:/Study/3rd-y/3rdY-Sem2/NT531.Q21-DanhGiaHieuNang/DoAn/demo-guide.md)**: The professional thesis demonstration script.
- **[agent-testing.md](file:///d:/Study/3rd-y/3rdY-Sem2/NT531.Q21-DanhGiaHieuNang/DoAn/agent-testing.md)**: The hardened AI testing prompt and command menu.

---

## 🌟 Acknowledgments

**🎓 Course:** NT531 - Network System Performance Evaluation
**🏫 Institution:** University of Information Technology (UIT)
**🤖 AI Partner:** Google Gemini AI Agentic Framework
