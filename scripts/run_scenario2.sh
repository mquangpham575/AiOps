#!/bin/bash

# ═══════════════════════════════════════════════════════════════
# Scenario 2: CPU Stress Auto-Remediation (TTR Analysis)
# ═══════════════════════════════════════════════════════════════

TARGET_URL="http://localhost:5000"
RESULTS_DIR="results/scenario2"
STRESS_DURATION=300
WORKERS=4

mkdir -p $RESULTS_DIR

echo "============================================================"
echo " 🔥 [SCENARIO-2] Manual vs AI-Assisted Auto-Remediation"
echo "============================================================"
echo " This test measures Mean Time To Recovery (MTTR)."
echo "------------------------------------------------------------"

# ── RUN 1: Manual Baseline ────────────────────────────────────
echo "🚀 [RUN 1/3] TYPE: Manual Baseline (Simulated SLA 5m)"
echo "   [ACTION] Please DISABLE the AI Agent now (docker stop aiops-agent)."
echo "   [ACTION] Press ENTER when ready to trigger stress..."
read

./scripts/trigger_cpu_stress.sh --duration $STRESS_DURATION --workers $WORKERS

echo ""
echo "   [STATUS] Manual run finished. Record the TTR for your report."
echo "   [ACTION] Please RE-ENABLE the AI Agent (docker start aiops-agent)."
echo "   [ACTION] Press ENTER to continue with AI runs..."
read

# ── RUN 2 & 3: AI Assisted ────────────────────────────────────
for i in {2..3}
do
    echo ""
    echo "🚀 [RUN $i/3] TYPE: AI-Assisted Auto-Remediation"
    ./scripts/trigger_cpu_stress.sh --duration $STRESS_DURATION --workers $WORKERS
    
    echo "   [STATUS] Run $i complete. Waiting 30s cooldown..."
    sleep 30
done

echo ""
echo "============================================================"
echo " 📊 [ANALYSIS] Parsing Agent Logs for TTR Breakdown"
echo "============================================================"
# Point 2: TTR breakdown (ensured)
# We assume logs are redirected or we read from docker logs
docker logs aiops-agent > $RESULTS_DIR/agent_run.log 2>&1
python3 scripts/parse_agent_logs.py $RESULTS_DIR/agent_run.log

echo "------------------------------------------------------------"
echo " ✅ Scenario 2 Demo Finished."
echo "============================================================"
