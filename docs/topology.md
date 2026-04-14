# AIOps PoC - Planned Distributed Topology

## Overview

This document describes the planned 3-node distributed topology for MTTR comparison between AI Agent (LLM-powered) and Rule-Based Agent.
Designed for **exact error attribution** and **uncontested metric measurement**.

> This is a target architecture plan. It describes the intended deployment layout, not the current implemented state.

- **Node 1** — Control Plane (PC): measurement-critical services only
- **Node 2** — Load Gen + Observability (Azure VM): k6, Grafana, Jaeger, OTel Collector
- **Node 3** — App Plane (Azure VM): system under test

---

## Node Layout

```
┌─ Node 1: Control Plane (PC, Home Network) ─────────────────────────────┐
│                                                                         │
│  Docker bridge: control-net                                             │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐                                    │
│  │ Prometheus   │  │ AlertManager │                                    │
│  │ :9090        │  │ :9093        │                                    │
│  └──────┬───────┘  └──┬───────┬───┘                                    │
│         │             │       │                                         │
│    eval rules    webhook   webhook                                      │
│         │             │       │                                         │
│         │       ┌─────┴───┐ ┌─┴────────────────┐                       │
│         │       │AI Agent │ │Rule-Based Agent   │                       │
│         │       │:8080    │ │:5001              │                       │
│         │       │OTel SDK │ │OTel SDK           │                       │
│         │       └────┬────┘ └───┬───────────────┘                       │
│         │            └────┬─────┘                                       │
│         │                 │ Docker SDK                                   │
│         │                 │ ssh tunnel → localhost:2375                  │
└─────────┼─────────────────┼─────────────────────────────────────────────┘
          │                 │
     scrape :80,       SSH :22 (Docker tunneled)
     :9100,:8080            │
          │                 │            ┌───────────────────┐
          │                 │            │ Google Gemini API  │
          │                 │            │ (HTTPS)            │
          │                 │            │ ← AI Agent only    │
          │                 │            └───────────────────┘
 ═════════╧═════════════════╧══════════════════════════════ Internet ═══
          │                 │
          ▼                 ▼
┌─ Azure: rg-aiops  |  Region: Southeast Asia ──────────────────────────┐
│                                                                        │
│  VNet: aiops-vnet 10.0.0.0/16                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Subnet: aiops-subnet 10.0.1.0/24                                │  │
│  │                                                                  │  │
│  │  ┌─ Node 3: App Plane (aiops-app) ───────────────────────────┐  │  │
│  │  │  VM Size: B2ps_v2 (ARM64)  |  OS: Ubuntu 22.04            │  │  │
│  │  │  Public IP: <APP_VM_IP>    |  Private IP: 10.0.1.4        │  │  │
│  │  │                                                            │  │  │
│  │  │  ┌──────────────┐  ┌───────────────┐                      │  │  │
│  │  │  │ target-app   │  │ node-exporter │                      │  │  │
│  │  │  │ :80 (Flask)  │  │ :9100         │                      │  │  │
│  │  │  │ OTel SDK     │  └───────────────┘                      │  │  │
│  │  │  └──────────────┘                                          │  │  │
│  │  │  ┌──────────────┐  ┌───────────────┐                      │  │  │
│  │  │  │ cAdvisor     │  │ Docker Daemon │                      │  │  │
│  │  │  │ :8080        │  │ unix:///var/  │                      │  │  │
│  │  │  └──────────────┘  │ run/docker.   │                      │  │  │
│  │  │                    │ sock (local)  │                      │  │  │
│  │  │                    └───────────────┘                      │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │       │                              ▲                           │  │
│  │       │ OTel traces (gRPC :4317)     │ k6 HTTP :80              │  │
│  │       │ private network              │ private network           │  │
│  │       ▼                              │                           │  │
│  │  ┌─ Node 2: Load Gen + Observability (aiops-loadgen) ────────┐  │  │
│  │  │  VM Size: B2s (x64)  |  OS: Ubuntu 22.04                  │  │  │
│  │  │  Public IP: <LOADGEN_VM_IP>  |  Private IP: 10.0.1.5      │  │  │
│  │  │                                                            │  │  │
│  │  │  ┌──────────┐  ┌────────────────┐  ┌──────────┐           │  │  │
│  │  │  │   k6     │  │ OTel Collector │  │  Jaeger  │           │  │  │
│  │  │  │ (bare    │  │ :4317 (gRPC)   │  │ :16686   │           │  │  │
│  │  │  │  host)   │  │ :4318 (HTTP)   │  │ (UI)     │           │  │  │
│  │  │  └──────────┘  └────────────────┘  └──────────┘           │  │  │
│  │  │  ┌──────────┐  ┌────────────────┐  ┌────────────┐         │  │  │
│  │  │  │ Grafana  │  │ node-exporter  │  │ Prometheus │         │  │  │
│  │  │  │ :3000    │  │ :9100          │  │ :9090      │         │  │  │
│  │  │  └──────────┘  └────────────────┘  └────────────┘         │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │                                                                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  NSG: aiops-app-nsg (applied to aiops-app NIC)                        │
│  ┌───────────┬──────┬────────────────────────────────────────┐        │
│  │ Port      │ Proto│ Source → Purpose                       │        │
│  ├───────────┼──────┼────────────────────────────────────────┤        │
│  │ 22        │ TCP  │ Admin IP only → SSH + Docker tunnel    │        │
│  │ 80        │ TCP  │ VNet + Admin IP → App traffic + k6     │        │
│  │ 9100      │ TCP  │ Admin IP only → node-exporter          │        │
│  │ 8080      │ TCP  │ Admin IP only → cAdvisor               │        │
│  └───────────┴──────┴────────────────────────────────────────┘        │
│                                                                        │
│  NSG: aiops-loadgen-nsg (applied to aiops-loadgen NIC)                │
│  ┌───────────┬──────┬────────────────────────────────────────┐        │
│  │ Port      │ Proto│ Source → Purpose                       │        │
│  ├───────────┼──────┼────────────────────────────────────────┤        │
│  │ 22        │ TCP  │ Admin IP only → SSH                    │        │
│  │ 4317      │ TCP  │ VNet + Admin IP → OTel Collector gRPC  │        │
│  │ 3000      │ TCP  │ Admin IP only → Grafana UI             │        │
│  │ 9090      │ TCP  │ Admin IP only → Prometheus (federate)  │        │
│  │ 16686     │ TCP  │ Admin IP only → Jaeger UI              │        │
│  │ 9100      │ TCP  │ Admin IP only → node-exporter          │        │
│  └───────────┴──────┴────────────────────────────────────────┘        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Why This Is Better Than the 2nd-Laptop Approach

| Problem with laptop                                        | Solved by Azure VM                                 |
| ---------------------------------------------------------- | -------------------------------------------------- |
| Laptop behind NAT — target-app can't push OTel traces back | Same VNet — private IP `10.0.1.5`, no NAT          |
| WiFi jitter affects k6 metrics push to Prometheus          | k6 → app goes over Azure internal network (~0.5ms) |
| Need to carry and set up a 2nd device                      | `terraform apply` spins it up in 2 minutes         |
| Manual firewall rules on Windows                           | NSG handles everything declaratively               |
| Can't leave it running overnight for long tests            | VM runs unattended, deallocate when done           |

### Key Advantage: Same VNet

Both Azure VMs share `10.0.1.0/24`. All VM-to-VM traffic stays on Azure's internal fabric:

```
k6 (10.0.1.5) ──HTTP──▶ target-app (10.0.1.4:80)         ~0.5ms RTT
target-app (10.0.1.4) ──gRPC──▶ OTel Collector (10.0.1.5:4317)  ~0.5ms RTT
```

No internet hop. No NAT. No tunnel. No packet loss from ISP routing.

---

## Data Flows

### Critical Path (affects MTTR measurement)

These flows are time-sensitive. Any delay here skews MTTR results.
All critical-path services run on PC (Node 1) — no contention from k6 or observability.

```
1. Prometheus ──eval rules──▶ AlertManager          (PC internal, ~ms)
2. AlertManager ──webhook──▶ AI Agent :8080          (PC internal, ~ms)
3. AlertManager ──webhook──▶ Rule-Based Agent :5001  (PC internal, ~ms)
4. AI Agent ──HTTPS──▶ Google Gemini API             (internet, ~1-5s)
5. AI Agent ──SSH tunnel──▶ Docker Daemon (Azure)    (internet, ~100ms)
6. Rule-Based Agent ──SSH tunnel──▶ Docker Daemon    (internet, ~100ms)
```

### Metrics Collection (background, non-blocking)

```
7.  Prometheus (PC) ──scrape──▶ target-app :80            (internet, 15s)
8.  Prometheus (PC) ──scrape──▶ node-exporter :9100       (internet, 15s)
9.  Prometheus (PC) ──scrape──▶ cAdvisor :8080            (internet, 15s)
10. Prometheus (PC) ──scrape──▶ AI Agent :8080            (PC internal, 15s)
11. Prometheus (PC) ──scrape──▶ Rule-Based Agent :5001    (PC internal, 15s)
12. Prometheus (PC) ──scrape──▶ loadgen node-exporter :9100  (internet, 15s)
```

> **New scrape target:** Line 12 is a new target that must be added to `config/prometheus/prometheus.yml`
> on the PC. Point it at `<LOADGEN_VM_IP>:9100`.
>
> **Timestamp skew:** PC scrapes Azure targets over the internet (~50-100ms per scrape),
> while loadgen Prometheus scrapes locally (~<1ms). The resulting timestamp offset between
> PC-collected and loadgen-collected metrics is bounded by the 15s scrape interval — negligible
> for MTTR analysis, but worth noting for sub-second trace correlation.

### Load Testing

```
13. k6 (loadgen VM) ──HTTP :80──▶ target-app (app VM)    (private network, ~0.5ms)
14. k6 ──remote-write──▶ Prometheus :9090 (loadgen VM)   (loadgen internal, periodic)
```

> **Note:** k6 uses `--out experimental-prometheus-rw` to push metrics directly to
> the local Prometheus. Prometheus must be started with `--web.enable-remote-write-receiver`
> to accept these pushes.

### Telemetry (async, non-blocking to source)

```
15. AI Agent (PC) ──gRPC :4317──▶ OTel Collector (loadgen VM)       (internet, async)
16. Rule-Based Agent (PC) ──gRPC :4317──▶ OTel Collector (loadgen)  (internet, async)
17. target-app (app VM) ──gRPC :4317──▶ OTel Collector (loadgen)    (private net, async)
18. OTel Collector ──export──▶ Jaeger                               (loadgen internal)
19. OTel Collector ──remote-write──▶ Prometheus (loadgen VM)        (loadgen internal)
```

### Federation (PC aggregates loadgen metrics)

```
20. Prometheus (PC) ──federate──▶ Prometheus :9090 (loadgen VM)    (internet, periodic)
```

> PC Prometheus federates from loadgen Prometheus to pull k6 + OTel-derived metrics
> into the unified MTTR view. **No port forwarding on the home router needed.**
> Only the loadgen VM's :9090 must be open in the NSG (Admin IP only).

### Visualization (after test, on-demand)

```
21. Grafana (loadgen VM) ──query──▶ Prometheus :9090 (loadgen VM)  (loadgen internal)
22. User browser ──▶ Grafana :3000 (loadgen public IP)             (internet, on-demand)
23. User browser ──▶ Jaeger :16686 (loadgen public IP)             (internet, on-demand)
```

> Grafana queries the local Prometheus on the same VM — no cross-internet dependency.

---

## Error Attribution Chain

### k6 Phase Breakdown (client-side)

```
Every k6 HTTP request records timing per phase:

  http_req_blocked     → queued waiting for free socket       (k6 internal)
  http_req_connecting  → TCP handshake to target              (network + app backlog)
  http_req_sending     → request body upload                  (network)
  http_req_waiting     → server processing time               (APP)
  http_req_receiving   → response body download               (network)
  http_req_duration    → total end-to-end                     (everything)
  http_req_failed      → did the request error?               (need correlation)
```

### OTel Traces (server-side)

```
Every request that REACHES the app produces a trace span:

  flask.request
    ├── start_time, end_time, status_code
    ├── error (if any)
    └── child spans (internal processing)
```

### Attribution Decision Tree

```
k6 reports an error for request X
│
├── OTel trace exists for request X on target-app?
│   ├── YES + trace has error     →  APP caused it
│   ├── YES + trace is 200 OK     →  Response lost in NETWORK
│   └── NO trace at all
│       │
│       ├── k6 http_req_blocked spiked?
│       │   └── YES  →  K6 socket exhaustion (K6 caused it)
│       │
│       ├── k6 http_req_connecting spiked?
│       │   └── YES  →  App TCP backlog full (APP caused it)
│       │
│       └── Neither spiked?
│           └── Packet dropped (NETWORK caused it)
│
└── Result: every error has exactly one owner
```

> **k6 ↔ OTel Trace Correlation:** k6 does not natively inject `traceparent` headers
> (that requires `xk6-distributed-tracing`). Correlation between a k6 request and its
> OTel trace is performed by **timestamp-window matching**: k6 records request start/end
> timestamps; the corresponding OTel span is the one whose `start_time` falls within
> that window (±scrape-interval tolerance). This is sufficient for thesis-level analysis
> where load is controlled and request rates are known.

---

## Per-Node Responsibilities

### Node 1: Control Plane (PC)

Only measurement-critical services. No visualization, no trace storage, no load generation.

| Service          | Port  | Memory     | Role                                                      |
| ---------------- | ----- | ---------- | --------------------------------------------------------- |
| Prometheus       | :9090 | 256MB      | Scrape all targets, evaluate alert rules, store MTTR data |
| AlertManager     | :9093 | 64MB       | Route alerts to both agents simultaneously                |
| AI Agent         | :8080 | 128MB      | LLM-powered incident response (Gemini + Docker SDK)       |
| Rule-Based Agent | :5001 | 64MB       | Deterministic baseline (rule table + Docker SDK)          |
| **Total**        |       | **~512MB** | **Critical path only**                                    |

### Node 2: Load Gen + Observability (Azure VM: aiops-loadgen)

Non-critical services. k6 and observability share because their workloads don't compete.

| Service        | Port         | Memory      | Role                                               |
| -------------- | ------------ | ----------- | -------------------------------------------------- |
| k6             | —            | ~200MB      | Load generation (bare host, not Docker)            |
| OTel Collector | :4317, :4318 | 128MB       | Receive traces, export to Jaeger + Prometheus      |
| Jaeger         | :16686       | 256MB       | Trace storage + visualization UI                   |
| Prometheus     | :9090        | 256MB       | Local TSDB for k6 + OTel metrics; federated by PC  |
| Grafana        | :3000        | 256MB       | Dashboard visualization (queries local Prometheus) |
| node-exporter  | :9100        | 32MB        | Monitor the load generator itself                  |
| **Total**      |              | **~1128MB** | **No impact on MTTR measurement**                  |

**Recommended VM:** B2s (2 vCPU, 4GB RAM, x64) — ~$15/month, deallocate when not testing.

> **Prometheus memory:** 256MB may be tight under sustained k6 load with high-cardinality
> metrics. Monitor `prometheus_tsdb_head_series` during test runs and increase to 384MB
> if needed.

### Node 3: App Plane (Azure VM: aiops-app)

System under test. Completely isolated from measurement and load generation infrastructure.

| Service       | Port  | Memory     | Role                                      |
| ------------- | ----- | ---------- | ----------------------------------------- |
| target-app    | :80   | 256MB      | Flask application under test              |
| node-exporter | :9100 | 32MB       | Host metrics (CPU, memory, disk, network) |
| cAdvisor      | :8080 | 128MB      | Container metrics                         |
| Docker Daemon | unix  | —          | Local socket; agents access via SSH tunnel|
| **Total**     |       | **~416MB** | **System under test — isolated**          |

**Target VM:** B2ps_v2 (2 vCPU ARM64, 8GB RAM) — to be provisioned.

> **Docker access via SSH tunnel:** The Docker daemon on the App VM listens on its
> Unix socket only (`/var/run/docker.sock`) — no TCP port exposed. PC agents connect
> through an SSH tunnel:
>
> ```bash
> ssh -N -L 2375:/var/run/docker.sock azureuser@<APP_VM_IP>
> ```
>
> Agents then use `DOCKER_HOST=tcp://localhost:2375`. This eliminates the unauthenticated
> Docker TCP API from the attack surface — access requires a valid SSH key.

---

## Network Requirements

### PC ↔ Azure (internet)

| Direction       | Flow                | Port              | Purpose                                   |
| --------------- | ------------------- | ----------------- | ----------------------------------------- |
| PC → App VM     | Prometheus scrape   | :80, :9100, :8080 | Collect metrics                           |
| PC → App VM     | Docker SDK (tunnel) | :22 (SSH)          | Agent remediation via SSH-tunneled Docker  |
| PC → Loadgen VM | OTel traces         | :4317             | Agent traces to collector                 |
| PC → Loadgen VM | Prometheus federate | :9090             | Pull k6 + OTel metrics into PC Prometheus |
| PC → Loadgen VM | Prometheus scrape   | :9100             | Loadgen node-exporter (host metrics)      |

> **No inbound traffic to PC required.** All flows are PC-initiated (outbound).
> k6 and OTel Collector write to the local Prometheus on the loadgen VM.
> Grafana queries it locally. PC federates from it for the unified MTTR view.

### App VM ↔ Loadgen VM (private network — same VNet)

| Direction     | Flow            | Port  | Purpose                        |
| ------------- | --------------- | ----- | ------------------------------ |
| Loadgen → App | k6 load traffic | :80   | HTTP load test (private IP)    |
| App → Loadgen | OTel traces     | :4317 | target-app traces to collector |

All traffic over `10.0.1.0/24` — no internet, no NAT, no NSG public rules needed.
Azure internal fabric: ~0.5ms RTT, consistent, no ISP jitter.

### NSG Rules (Updated)

**App VM (aiops-app) — NSG: aiops-app-nsg:**

| Port | Source                        | Purpose                               |
| ---- | ----------------------------- | ------------------------------------- |
| 22   | Admin IP                      | SSH + Docker tunnel from PC agents    |
| 80   | VNet (10.0.0.0/16) + Admin IP | App traffic from k6 (private) + admin |
| 9100 | Admin IP                      | node-exporter scrape from PC          |
| 8080 | Admin IP                      | cAdvisor scrape from PC               |

**Loadgen VM (aiops-loadgen) — NSG: aiops-loadgen-nsg:**

| Port  | Source                        | Purpose                                 |
| ----- | ----------------------------- | --------------------------------------- |
| 22    | Admin IP                      | SSH                                     |
| 4317  | VNet (10.0.0.0/16) + Admin IP | OTel gRPC from app VM + PC agents       |
| 3000  | Admin IP                      | Grafana UI                              |
| 9090  | Admin IP                      | Prometheus (federation from PC + admin) |
| 16686 | Admin IP                      | Jaeger UI                               |
| 9100  | Admin IP                      | node-exporter scrape from PC            |

---

## Cost Estimate

| Resource               | Size    | Monthly (running 24/7) | With deallocate                 |
| ---------------------- | ------- | ---------------------- | ------------------------------- |
| aiops-app (existing)   | B2ps_v2 | ~$35                   | ~$5-10 (test days only)         |
| aiops-loadgen (new)    | B2s     | ~$15                   | ~$3-5 (test days only)          |
| Public IPs (2x static) | —       | ~$7                    | ~$7 (charged even when stopped) |
| **Total**              |         | **~$57**               | **~$15-22**                     |

Deallocate both VMs after each test session with `aiops-power.ps1` to stay within student credits.

---

## Thesis Validation Claim

> "The evaluation employs a 3-node distributed topology with strict workload isolation.
> Load generation and the system under test share an Azure VNet for deterministic
> network conditions (~0.5ms RTT), while the measurement infrastructure runs on a
> dedicated control plane with <20% resource utilization during all tests. Error
> attribution is achieved through cross-correlation of k6 HTTP phase metrics,
> OpenTelemetry distributed traces, and per-node resource monitoring (node-exporter
> on all 3 nodes), enabling deterministic classification of every observed error as
> application-side, client-side, or network-side."
