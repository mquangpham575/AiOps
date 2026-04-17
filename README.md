# Agentic AIOps
## The Autonomous Remediation Framework for Distributed Ecosystems

---

### Overview
**Agentic AIOps** is a distributed orchestration framework that leverages Large Language Models (LLMs) to automate the detection, analysis, and remediation of system incidents in real-time. By bridging the gap between observability and corrective action, the system achieves sub-minute Mean Time To Recovery (MTTR) for complex failure signatures across a 3-node Azure cluster.

---

### Architecture: The Observe-Reason-Act Lifecycle

```mermaid
graph TD
    A[Distributed Nodes] -->|Metrics| B(Prometheus)
    B -->|Alerts| C{AI Agent}
    C -->|Reasoning| D[Decision Engine]
    D -->|Autonomous Toolbelt| E[Remediation Action]
    E -->|Restore Baseline| A
```

#### Technical Stack Matrix
| Component | Technology | Role |
| :--- | :--- | :--- |
| **Orchestration** | Gemini-Native AI Agent (Python) | LLM Reasoning & SSH Tooling |
| **Observability** | Prometheus (v2.x), AlertManager | Metric Scraping & Alert Propagation |
| **Visualization** | Grafana (Dashboards-as-Code) | 1-minute real-time telemetry |
| **Load Testing** | Locust, stress-ng, DDoS Engine | Failure Scenario Synthesis |
| **Infrastructure** | Azure VMs (B2s), Docker, Compose | Distributed Node Hosting |

---

### Detailed Cluster Topology & Network Matrix
The environment is synchronized across a 3-node Azure VNet (`10.0.1.0/24`). 

| Node | Public IP | Role | Critical Internal Ports |
| :--- | :--- | :--- | :--- |
| **Node 1** | `104.215.158.157` | **Control Plane** | `3000` (Grafana), `9090` (Promet), `9093` (AM), `8083` (Agent) |
| **Node 2** | `104.215.191.69` | **Load Generator** | `8089` (Locust), `9091` (Pushgateway) |
| **Node 3** | `4.194.57.3` | **Application Node** | `80` (App), `9100` (Node Exp), `8080` (cAdvisor) |

---

### Repository Structure
```text
DoAn/
├── src/                          # Application & Agent Logic
│   ├── agent/                    # AI & Rule-based Remediation Engines
│   └── app/                      # Target Flask Application
├── ops/                          # Infrastructure & Observability
│   ├── infra/                    # Docker Compose Deployment Specs
│   └── monitoring/               # Prometheus, Grafana, AlertManager Configs
├── tests/                        # Validation & Performance Suites
│   └── performance/              # Locust Scenarios (scenarios.yml)
├── scripts/                      # Orchestration & Power Control
│   ├── aiops-power.ps1           # Azure VM & Docker Lifecycle
│   └── demo_runner.py            # Automated Validation Suite
└── README.md                     # Master Technical Manual
```

---

### Remediation Scenarios: Technical Deep-Dive

#### 1. CPU Core Saturation (High-Precision Kill)
- **Signature**: 100% Core saturation via `stress-ng`.
- **Reasoning**: Agent differentiates between system stress and application load.
- **Action**: `auto_kill_cpu_stress` targets specific stress binaries via remote SSH.

#### 2. Memory Exhaustion (State Restoration)
- **Signature**: Recursive OOM leak and P99 latency degradation.
- **Reasoning**: Correlation of RAM saturation with application throughput drop.
- **Action**: `restart_service` to purge the container memory space.

#### 3. Network Brute-Force (Resilience Audit)
- **Signature**: 60+ RPS parallel request flood.
- **Reasoning**: Monitoring of success/error rates to identify DDoS signatures.
- **Action**: `restart_service` + connection clearing for baseline recovery.

---

### Telemetry Access Matrix
Comprehensive links to the live observability suite:

| Interface | URL | Purpose |
| :--- | :--- | :--- |
| **Grafana Suite** | [http://104.215.158.157:3000](http://104.215.158.157:3000) | Full system health dashboards |
| **Prometheus UI** | [http://104.215.158.157:9090](http://104.215.158.157:9090) | Metric targets and alert status |
| **AI Action Log** | [http://104.215.158.157:8083/logs/ui](http://104.215.158.157:8083/logs/ui) | Real-time Gemini reasoning log |
| **AlertManager** | [http://104.215.158.157:9093](http://104.215.158.157:9093) | Active incident propagation status |

---

### Administrative Governance
- [**Thesis Demo Script**](./demo-guide.md): Standardized demonstration procedures.
- [**Development Context**](https://github.com/mquangpham575/AiOps): Source Control Repository.

### Academic Affiliation
Developed for **NT531: Network System Performance Evaluation** at the **University of Information Technology (UIT)**.
