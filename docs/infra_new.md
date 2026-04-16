# [OBSOLETE] AIOps Infrastructure Upgrade Plan
## Single-Node → PC + Azure VM Distributed Architecture

> **This document is obsolete.** The current architecture uses 3 Azure VMs (Control, LoadGen, App) — not the PC + Azure VM hybrid described here. See `docs/topology.md` for the current topology.

---

## 1. Motivation

The current deployment runs all 7 Docker services on a single Windows PC connected via one bridge network (`aiops-net`). This is sufficient for development but weak for a thesis defense. Likely professor challenges:

| Challenge | Root Cause | This Plan's Answer |
|---|---|---|
| "Not realistic — one machine" | Single-node topology | Genuine two-machine deployment (PC + Azure VM) |
| "How do you prove AI is faster?" | No baseline comparison | `rule-based-agent` runs same alerts; MTTR measured for both |

**Cost:** $0 — covered by Visual Studio Enterprise ($150/mo Azure credit) + Azure for Students ($100 free credit). A B2s VM costs ~$35/month, well within both limits.

---

## 2. Architecture

### 2.1 Before (Current)

```
┌─────────────────── Single PC (Docker bridge: aiops-net) ──────────────────┐
│                                                                             │
│  [Locust] → [target-app:5000]                                              │
│               ↓ /metrics                                                   │
│  [Prometheus:9090] ← [node-exporter:9100] [cadvisor:8080]                 │
│               ↓                                                            │
│  [AlertManager:9093] → POST /webhook                                       │
│               ↓                                                            │
│  [AI Agent:8080] → docker.sock → [target-app]                             │
│  [Grafana:3000]  ← Prometheus                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Weaknesses:** Single host, single target, no log pipeline, no MTTR baseline.

### 2.2 After (Target)

```
┌─── PC — Control Plane ──────────────────────────────────────────────────┐
│                                                                          │
│  [Prometheus:9090]  ←── scrapes Azure VM remotely (public IP)           │
│  [AlertManager:9093] ──► fans out to BOTH agents simultaneously         │
│  [Grafana:3000]     ←── Prometheus (MTTR dashboard)                     │
│  [AI Agent:8080]    ──► SSH tunnel → Azure VM Docker socket             │
│  [Rule-Based Agent:5001] ──► SSH tunnel → Azure VM (same mechanism)     │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
         ↕  Public Internet
         ↕  Prometheus scrapes :80 :8080 :9100
         ↕  Agents control Docker via SSH tunnel (:22)
         ↕  Load test traffic → :80
┌─── Azure VM B2s — Application Plane ───────────────────────────────────┐
│                                                                          │
│  [target-app:80]       ← scraped by Prometheus, hit by Locust           │
│  [node-exporter:9100]  ← scraped by Prometheus on PC                    │
│  [cadvisor:8080]       ← scraped by Prometheus on PC                    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Key Data Flows

| Flow | Direction | Protocol | Ports |
|---|---|---|---|
| Prometheus → node-exporter | PC → Azure | HTTP pull | 9100 |
| Prometheus → cadvisor | PC → Azure | HTTP pull | 8080 |
| Prometheus → target-app | PC → Azure | HTTP pull | 80 |
| Agent → Docker daemon | PC → Azure | SSH tunnel | 22 |
| AlertManager → AI Agent | PC → PC | HTTP | 8080 |
| AlertManager → Rule-Based Agent | PC → PC | HTTP | 5001 |
| Locust load test → target-app | Any → Azure | HTTP | 80 |

---

## 3. Critical Design Decisions

### 3.1 Remote Docker Control via SSH Tunnel

The AI agent uses `docker.from_env()` (Docker Python SDK), which automatically reads the `DOCKER_HOST` environment variable. An SSH tunnel forwards `localhost:2375` to the remote Docker Unix socket:

```bash
ssh -N -L 2375:/var/run/docker.sock azureuser@<AZURE_VM_IP>
```

Agents use `DOCKER_HOST=tcp://host.docker.internal:2375` — all Docker SDK calls (`container.restart()`, `container.top()`, `container.exec_run()`) transparently target the Azure VM through the tunnel. No Docker TCP port is exposed on the VM; access requires a valid SSH key.

### 3.2 Removing Obsolete Tools

`block_ip` and `apply_rate_limit` tools expect to run `iptables` locally, which won't work in a remote setup. Since this is a school project and those actions cannot easily target the VM without extra sidecars, these tools will be completely deleted from the AI Agent to keep the architecture simple and eliminate dead code.

### 3.3 AlertManager Fan-Out (Both Agents Simultaneously)

AlertManager's `all-agents` receiver contains **both** webhook configs. Every alert hits both agents with identical payloads at the same time — this is the prerequisite for a fair MTTR comparison.

```yaml
receivers:
  - name: all-agents
    webhook_configs:
      - url: http://agent:8080/webhook        # AI agent
      - url: http://rule-based-agent:5001/alert  # Baseline
```

### 3.4 MTTR Measurement Strategy

Two distinct metrics per agent — labelled correctly for thesis defense:

| Metric | Formula | What it proves |
|---|---|---|
| `agent_response_latency_seconds` | `action_taken_at − webhook_received_at` | AI reasoning overhead vs. rule-based speed |
| `agent_mttr_seconds` | `action_taken_at − alert_started_at` | End-to-end incident response time |

- `alert_started_at` is taken from the `startsAt` field in the AlertManager webhook payload (already present, no extra instrumentation needed).
- `action_taken_at` is recorded immediately after the tool call returns.

**Expected values:**
- Rule-based: latency ~0.1–0.3s | MTTR ~30–60s (Prometheus `for:` delay + restart time)
- AI agent: latency ~3–8s | MTTR ~35–65s

The latency gap (~5–30×) is the headline thesis result. MTTR is near-equal — which is the *correct* finding: AI adds reasoning overhead but doesn't worsen repair time.

Both agents expose:
- `agent_response_latency_seconds` (Gauge)
- `agent_mttr_seconds` (Gauge)

with a `agent_type="ai"` or `agent_type="rule"` label so one dashboard query covers both.

---

## 4. New Files to Create

| File | Purpose |
|---|---|
| `docker-compose.control.yml` | PC services: prometheus, alertmanager, grafana, agent, rule-based-agent |
| `docker-compose.app.yml` | Azure VM services: target-app, node-exporter, cadvisor |
| `rule-based-agent/agent.py` | Deterministic webhook receiver — alert→action rule table, no LLM |
| `rule-based-agent/Dockerfile` | Same Python base as `agent/`, minus google-genai |
| `rule-based-agent/requirements.txt` | flask, requests, docker, prometheus-flask-exporter |
| `grafana/dashboards/mttr-comparison.json` | Latency comparison + MTTR (Row 1 priority, others nice-to-have) |

---

## 5. Files to Modify

| File | What Changes |
|---|---|
| `prometheus/prometheus.yml` | Add `node-exporter-azure` and `cadvisor-azure` scrape jobs pointing to `<AZURE_IP>`; update `target-app` job to `<AZURE_IP>:80`; add `rule-based-agent` job at port 5001 |
| `prometheus/alert.rules.yml` | Add `HighContainerRestartRate` alert with `for: 2m` |
| `alertmanager/alertmanager.yml` | Rename receiver to `all-agents`; add second webhook config for rule-based-agent:5001 |
| `agent/tools.py` | Delete `block_ip` and `apply_rate_limit` tools entirely |
| `agent/agent.py` | Add `agent_response_latency_seconds` and `agent_mttr_seconds` Prometheus Gauges (label `agent_type="ai"`); set both after tool execution using `webhook_received_at` and `startsAt` from payload |
| `docker-compose.*.yml` | Hardcode Azure VM/PC IPs directly in compose configs to avoid `.env` management overhead |

---

## 6. Implementation Phases

### Phase 1 — Azure VM Provisioning
1. Create VM: Ubuntu 22.04 LTS, size B2s (2 vCPU, 4GB RAM), generate SSH key pair
2. Install Docker Engine via official apt repository; add user to `docker` group
3. Docker daemon listens on Unix socket only (default) — no TCP exposure needed.
   Remote access is via SSH tunnel:
   ```bash
   ssh -N -L 2375:/var/run/docker.sock azureuser@<AZURE_VM_IP>
   ```
   The `aiops-power.ps1` script manages tunnel lifecycle automatically.
4. Configure NSG (see Section 7 for full port table)
5. **Gate:** SSH tunnel active + `docker ps` via tunnel returns empty list

### Phase 2 — Application Plane (Azure VM)
1. Create `docker-compose.app.yml` (target-app + node-exporter + cadvisor)
2. Copy/clone project to Azure VM.
3. `docker compose -f docker-compose.app.yml up -d` on Azure VM
4. **Gate:** `curl http://<AZURE_IP>/` → 200; `curl http://<AZURE_IP>:9100/metrics` from PC → Prometheus text

### Phase 3 — Control Plane Config (PC)
1. Modify `prometheus/prometheus.yml` — add Azure VM scrape targets
2. Modify `prometheus/alert.rules.yml` — add new alert
3. Modify `alertmanager/alertmanager.yml` — fan-out to both agents
4. Create `docker-compose.control.yml` with all 5 PC services
5. **Gate:** `docker compose -f docker-compose.control.yml up -d`; all targets `UP` at `:9090/targets`

### Phase 4 — New Services + Agent Patches
1. Build `rule-based-agent/` directory (agent.py, Dockerfile, requirements.txt)
2. Modify `agent/tools.py` — delete `block_ip` and `apply_rate_limit` functions entirely
3. Modify `agent/agent.py` — add `agent_response_latency_seconds{agent_type="ai"}` and `agent_mttr_seconds{agent_type="ai"}` Prometheus gauges
4. Rebuild containers: `docker compose -f docker-compose.control.yml up -d --build`
5. **Gate:** `:8080/health` and `:5001/health` both return `{"status":"ok"}`

### Phase 5 — MTTR Grafana Dashboard
1. Create `grafana/dashboards/mttr-comparison.json` (see Section 8 for panel layout)
2. Reload Grafana provisioning: `docker restart grafana`
3. **Gate:** Dashboard renders; run one load test scenario → both MTTR series populate

### Phase 6 — Integration Validation
1. Trigger `ContainerHighCPU` scenario on Azure VM
2. Confirm AlertManager fires → both agents receive alert within 10s
3. Confirm AI agent calls `restart_service` → `ssh azureuser@<AZURE_IP> 'docker logs target-app'` shows restart
4. Confirm rule-based agent does same independently
5. Check MTTR overlay panel: rule-based ~0.1–0.3s, AI agent ~3–8s — visible separation

---

## 7. rule-based-agent Design

**Webhook endpoint:** `POST /alert` (same AlertManager payload schema as main agent)

**Rule table (static mapping, no LLM):**

| Alert | Action |
|---|---|
| `ContainerHighCPU` | `restart_service` |
| `HighCPUUsage` | `restart_service` |
| `HighMemoryUsage` | `restart_service` |
| `CriticalSystemLoad` | `restart_service` |
| `HighSystemLoad` | `reduce_system_load` |
| `HighRequestLatency` | `log_only` |
| `HighRequestRate` | `log_only` |
| `HighContainerRestartRate` | `log_only` |
| `default` | `log_only` |

**Idempotency cooldown (prevents double-restart with AI agent):**

```python
import time
_cooldown: dict[str, float] = {}   # (alert+container) → last_action_ts

def is_on_cooldown(key: str, ttl: int = 30) -> bool:
    return time.time() - _cooldown.get(key, 0) < ttl

def set_cooldown(key: str):
    _cooldown[key] = time.time()
```

The rule-based agent checks `is_on_cooldown(f"{alertname}:{container}")` before acting. This prevents double-fires. The AI agent naturally takes longer to respond due to LLM latency, implicitly preventing simultaneous double-restarts without needing explicit cooldown logic.

**Log entry schema** (matches main agent — same dashboard queries work for both):
```json
{
  "timestamp": "<ISO8601>",
  "webhook_received_at": "<ISO8601>",
  "alert": "<alertname>",
  "scenario": "<label>",
  "action": "<tool_name>",
  "result": "<outcome string>",
  "latency_ms": 120
}
```

**Endpoints:** `POST /alert`, `GET /logs`, `GET /health`, `GET /metrics`

**Prometheus gauges:** `agent_response_latency_seconds{agent_type="rule"}` and `agent_mttr_seconds{agent_type="rule"}` — updated after every action execution.

---

## 8. MTTR Comparison Dashboard Layout

### Row 1 — Headline Thesis Metric
| Panel | Type | Datasource | Query |
|---|---|---|---|
| Latency Overlay (both agents) | Time series | Prometheus | `agent_response_latency_seconds` (legend: `{{agent_type}}`) |
| MTTR Overlay (both agents) | Time series | Prometheus | `agent_mttr_seconds` (legend: `{{agent_type}}`) |

### Row 2 — Target Container Health (Nice-to-have)
| Panel | Type | Datasource | Query |
|---|---|---|---|
| Container CPU | Time series | Prometheus | `container_cpu_usage_seconds_total{name="target-app"}` |
| Container Memory | Time series | Prometheus | `container_memory_usage_bytes{name="target-app"}` |

**Annotations:**
- (Optional) Use local Grafana annotations mapped to agent `/logs` API if desired, but not required for demo.

---

## 9. Azure NSG Port Table

| Port | Protocol | Service | Source |
|---|---|---|---|
| 22 | TCP | SSH + Docker tunnel | Admin IP only |
| 80 | TCP | Nginx / target-app traffic | Any (load test) |
| 8080 | TCP | cAdvisor scrape | Admin IP only |
| 9100 | TCP | node-exporter scrape | Admin IP only |

**Port 5000 is NOT exposed.** All target-app traffic routes through nginx on port 80 only.

---

## 10. End-to-End Verification Checklist

| # | Check | How | Expected |
|---|---|---|---|
| 1 | Prometheus scraping Azure | `:9090/targets` | All Azure jobs `UP` |
| 2 | Both agents healthy | `:8080/health`, `:5001/health` | `{"status":"ok"}` |
| 3 | AlertManager fan-out | Trigger alert → check both `/logs` | Both show new entry |
| 4 | Remote Docker control | Trigger restart → check Azure container logs | Container restart event visible |
| 5 | MTTR separation | Run load test → check overlay panel | Rule-based < 0.5s, AI ~3–8s |
