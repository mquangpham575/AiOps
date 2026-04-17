# 🏁 AIOps Thesis Demonstration Guide

This guide provides a step-by-step script for demonstrating the autonomous remediation capabilities of the AIOps Agentic System.

---

## 🏗 Demo Setup & Preparation

1.  **Dashboard Hub**: Open the [Cluster Observability Dashboard](http://104.215.158.157:3000) in your browser.
2.  **Logic Trace**: Open the [AI Action Log](http://104.215.158.157:8083/logs/ui) to see real-time reasoning.
3.  **Baseline Verification**: Confirm the **"RPS"** (Traffic) is quiet and **"App CPU"** is near 0%.

---

## 🚨 Scenario 01: Intelligent CPU Remediation

**Goal**: Demonstrate how the AI Agent identifies and kills specific high-CPU stress processes without taking the entire server down.

1.  **Trigger**: Run the CPU flood command from your local terminal:
    ```bash
    python scripts/demo_runner.py --scenario cpu_flood --iterations 1 --duration 120
    ```
2.  **Observe (Grafana)**:
    - Watch **"Container CPU Usage (%)"** spike to 100%.
    - Wait ~30-45 seconds for the `ContainerHighCPU` alert to fire.
3.  **Observe (AI Log)**:
    - See the Agent reason about the "stress-ng" processes.
    - Confirm the tool execution: `auto_kill_cpu_stress`.
4.  **Verify**:
    - Watch the CPU usage drop back to normal in Grafana.
    - Note the **MTTR** (Recovery Time) on the comparison dashboard.

---

## 🚨 Scenario 02: Memory Exhaustion Recovery

**Goal**: Demonstrate the Agent's ability to recover from "Memory Leaks" by performing a clean service restart.

1.  **Trigger**: Run the memory leak command:
    ```bash
    python scripts/demo_runner.py --scenario memory_leak --iterations 1 --duration 120
    ```
2.  **Observe (Grafana)**:
    - Watch **"Container Memory %"** climb toward 80-90%.
    - Observe the secondary spike in **"P99 Latency"** as the app slows down.
3.  **Observe (AI Log)**:
    - The Agent identifies "High Memory" and "High Latency".
    - It decides to perform `restart_service`.
4.  **Verify**:
    - Watch the Memory and Latency metrics drop to baseline.

---

## 🚨 Scenario 03: Brute-Force DDoS Mitigation

**Goal**: Demonstrate high-throughput handling and real-time recovery tracking.

1.  **Trigger**: Run the brute-force parallel flood:
    ```bash
    # From LoadGen node (scripts handle this)
    python scripts/demo_runner.py --scenario ddos --iterations 1 --duration 120
    ```
2.  **Observe (Grafana)**:
    - Watch **"Current Traffic (RPS)"** and **"Throughput Mountain"** spike to 60+ req/s.
3.  **Observe (AI Log)**:
    - The Agent enters "Recovery Tracking" mode to monitor the normalization.
    - Note the tool execution: `restart_service` (to clear saturated connections).
4.  **Verify**:
    - Confirm the **Success Rate** climbs on the "MTTR Comparison" dashboard.

---

## 🏆 Presentation Conclusion

Point to the **"MTTR: AI vs Rule vs Human"** graph to show that the AI Agent recovered the system in under **60 seconds**, whereas a manual human response (baseline) would typically take 5-10 minutes.
