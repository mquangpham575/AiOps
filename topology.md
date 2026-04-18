# Agentic AIOps Hybrid Topology
## Unified Repository & Cluster Architecture

This diagram visualizes the mapping between the repository source code and the physical 3-node Azure cluster deployment.

```mermaid
graph TB
    subgraph local [Orchestration Layer]
        power[Cluster Controller]
        runner[Automation Suite]
    end

    subgraph node1 [Node 1: Control Plane]
        subgraph ops_mon [Observability Stack]
            prom[Prometheus]
            graf[Grafana]
            am[AlertManager]
        end
        subgraph agent_code [Remediation Engine]
            agent[AI Agent]
        end
    end

    subgraph node2 [Node 2: Load Generator]
        subgraph test_code [Failure Synthesis]
            locust[Locust Engine]
            pushgw[Pushgateway]
        end
    end

    subgraph node3 [Node 3: Application Node]
        subgraph app_code [Production Workload]
            flask[Target Flask App]
        end
        cadvisor[Container Metrics]
        node_exp[Host Metrics]
    end

    %% Deployment/Orchestration
    power -->|Orchestrate| node1
    power -->|Orchestrate| node2
    power -->|Orchestrate| node3
    
    %% Traffic & Stress
    locust -->|Inject Failure| flask
    
    %% Observability Flow
    prom -->|Scrape| node_exp
    prom -->|Scrape| cadvisor
    prom -->|Scrape| pushgw
    locust -->|Push Metrics| pushgw
    
    %% Alerting & Remediation
    prom -->|Raise Alert| am
    am -->|Notification| agent
    agent -->|Remediate - SSH| flask
    agent -->|Annotate| graf
    
    %% Visualization
    graf -->|Query| prom
```

### Component Definition & Repo Mapping

| Functional Component | Purpose | Repository Location |
| :--- | :--- | :--- |
| **Cluster Controller** | Automated VM and container lifecycle. | `aiops-power.ps1` |
| **Observability Stack** | Multi-layer metric collection and alerting. | `ops/monitoring/` |
| **AI Reasoning Engine** | LLM-based root cause analysis & remediation. | `src/agent/ai-agent/` |
| **Failure Synthesis** | Simulates CPU/RAM/Network failure scenarios. | `tests/performance/` |
| **Production Workload** | The target application being monitored. | `src/app/` |
