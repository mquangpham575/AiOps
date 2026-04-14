#!/bin/bash

# ═══════════════════════════════════════════════════════════════
# Scenario 3: DDoS Rate Limiting Trade-off Evaluation
# ═══════════════════════════════════════════════════════════════

TARGET_URL="http://localhost:5000"
RESULTS_DIR="results/scenario3"
DURATION="300s" # 5 mins

mkdir -p $RESULTS_DIR

echo "============================================================"
echo " 🌐 [SCENARIO-3] DDoS Mitigation vs Collateral Damage"
echo "============================================================"
echo " This test evaluates the effectiveness of iptables rate limits."
echo "------------------------------------------------------------"

CONFIGS=("nolimit" "limit100" "limit20")

for config in "${CONFIGS[@]}"
do
    echo ""
    echo "🚀 [CONFIG: $config] Starting Phase..."
    
    # ── Set rate limit ────────────────────────────────────────
    if [ "$config" == "nolimit" ]; then
        ./scripts/set_rate_limit.sh --clear
    elif [ "$config" == "limit100" ]; then
        ./scripts/set_rate_limit.sh --limit 100
    elif [ "$config" == "limit20" ]; then
        ./scripts/set_rate_limit.sh --limit 20
    fi
    
    # ── Run Load Test ─────────────────────────────────────────
    echo "   [ACTION] Running Locust (1100 users: 1000 Attack / 100 Legit)..."
    locust -f tests/performance/locustfile_scenario3.py \
        --headless \
        --users 1100 \
        --spawn-rate 100 \
        --host $TARGET_URL \
        --run-time $DURATION \
        --csv=$RESULTS_DIR/run_${config} \
        --only-summary
        
    echo "   [STATUS] Configuration $config finished. Waiting 30s cooldown..."
    sleep 30
done

# Clear everything at the end
./scripts/set_rate_limit.sh --clear

echo ""
echo "============================================================"
echo " 📊 [TRADE-OFF ANALYSIS] Mitigation vs User Impact"
echo "============================================================"
# Point 2: Aggregation (ensured)
python3 scripts/aggregate_scenario3.py $RESULTS_DIR

echo "------------------------------------------------------------"
echo " ✅ Scenario 3 Demo Finished."
echo "============================================================"
