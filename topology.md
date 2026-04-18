# Agentic AIOps: High-Level Architecture Design Spec
## Professional Diagram Guide (Draw.io / LucidChart)

This document serves as the visual specification for building a professional architecture diagram. Use the following layers and logic to represent the system accurately for your thesis.

---

### 1. Visual Topology (Mermaid Preview)

```mermaid
graph TB
    %% Tầng 1: Human & Orchestration
    subgraph Layer_1 [Human & Admin Layer]
        Admin((Administrator))
        Orchestrator[<b>Orchestration Suite</b><br/>Azure Controller / Demo Runner]
    end

    %% Tầng 2: Control Plane (The Brain)
    subgraph node1 [Node 1: Control Plane / Management]
        subgraph Docker_1 [Docker Host]
            prom[Prometheus Hub]
            am[AlertManager]
            pushgw[Pushgateway]
            graf[Grafana UI]
            agent[<b>AI Remediation Engine</b><br/>Gemini-Powered Agent]
        end
    end

    %% Tầng 3: Data Plane & Chaos
    subgraph Layer_3 [Execution Layer]
        subgraph node2 [Node 2: Chaos Engineering]
            subgraph Docker_2 [Docker Host]
                locust[<b>Chaos Launcher</b><br/>Locust Engine]
            end
        end

        subgraph node3 [Node 3: Production Victim]
            subgraph Docker_3 [Docker Host]
                flask[Target Flask App]
                exporters[Telemetry Exporters<br/>NodeExp / cAdvisor]
            end
        end
    end

    %% External AI
    Gemini{{Gemini Pro API}}

    %% Connections
    Admin -->|Triggers| Orchestrator
    Orchestrator -->|Deploy| node1 & node2 & node3
    
    %% Flows
    locust -. "1. Inject Fault (Red)" .-> flask
    exporters -- "2. Monitor (Blue)" --> prom
    prom -- "3. Alert (Orange)" --> am
    am -- "4. Webhook" --> agent
    agent <==> Gemini
    agent == "6. Remediate (Green)" ==> flask
    agent -. "7. Audit" .-> graf
```

---

### 2. Draw.io Design Instructions

#### A. Layered Structure
*   **Layer 1 (Top)**: Place the **User/Admin** icon. Connect it to the Orchestration tools.
*   **Layer 2 (Middle)**: The **Control Plane (Node 1)**. This is your largest box. It should house the observability stack and the AI Agent.
*   **Layer 3 (Bottom)**: Place **Node 2 (Chaos)** on the left and **Node 3 (Victim)** on the right to show clear separation of concern.

#### B. Professional Iconography
| Component | Draw.io Icon (Recommended) | Visual Note |
| :--- | :--- | :--- |
| **Nodes (VMs)** | Azure Virtual Machine (Blue cube) | Use the official Azure Stencil. |
| **Docker** | Docker Whale | Place as a background container inside each VM. |
| **AI Agent** | Brain / Robot / Sparkle | Use a distinct color (Red or Neon Gold). |
| **Failure** | Lightning Bolt / Fire | Place near the Chaos Launcher (Locust). |
| **Gemini** | Cloud / Star | Place in the 'Cloud' area outside your VNet. |

#### C. Color-Coded Flow Logic (The "Threads")
Use the following colors for connections to make the diagram readable:
*   🔴 **Red (Chaos/Attack)**: From Locust to Flask App. (Label: "Inject Fault").
*   🔵 **Blue (Observability)**: From App Exporters to Prometheus. (Label: "Scrape Telemetry").
*   🟠 **Orange (Alerting)**: From AlertManager to AI Agent. (Label: "Webhook Notification").
*   🟢 **Green (Recovery)**: From AI Agent to Flask App via SSH. (Label: "**Autonomous Remediation**").
*   🟣 **Purple (Reasoning)**: Between AI Agent and Gemini API.

---

### 3. Functional Component Descriptions

| Component | Functional Label | Thesis Role |
| :--- | :--- | :--- |
| **Locust** | Chaos Synthesis Engine | Synthesizes complex failure signatures (DDoS, OOM, CPU Saturation). |
| **Prometheus** | Temporal Data Hub | Aggregates time-series data and evaluates incident rules. |
| **AI Agent** | Remediation Orchestrator | Performs LLM-based root cause analysis and executes corrective SSH commands. |
| **Grafana** | Visualization & Audit | Provides real-time health metrics and intervention audit logs. |
| **Flask App** | Target Workload | Microservice baseline representing the production ecosystem. |
