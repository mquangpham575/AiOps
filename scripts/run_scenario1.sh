#!/bin/bash

# ═══════════════════════════════════════════════════════════════
# Scenario 1: Baseline vs Load Comparison Runner
# ═══════════════════════════════════════════════════════════════

TARGET_URL="http://localhost:5000"
RESULTS_DIR="results/scenario1"
DURATION="300"           # 5 minutes duration
NUM_REQUESTS=1000        # Target requests per run (Point 1 ensured)
ITERATIONS=3             # Run 3 times (Point 1 ensured)
COOLDOWN=30              # 30s between runs

mkdir -p $RESULTS_DIR

echo "============================================================"
echo " 🎯 [SCENARIO-1] Baseline vs Load Performance Evaluation"
echo "============================================================"
echo " Target: $TARGET_URL"
echo " Config: $ITERATIONS iterations x $NUM_REQUESTS requests"
echo "------------------------------------------------------------"

for i in $(seq 1 $ITERATIONS)
do
    TIMESTAMP=$(date +"%H:%M:%S")
    echo ""
    echo "🚀 [RUN $i/$ITERATIONS] Starting at $TIMESTAMP"
    
    # ── PHASE A: Baseline ─────────────────────────────────────
    # We use 1 user to ensure we can actually hit the target requests count
    echo "   [PHASE A] Starting Baseline (1 user)..."
    locust -f tests/performance/locustfile_scenario1.py \
        --headless \
        --users 1 \
        --spawn-rate 1 \
        --host $TARGET_URL \
        --run-time "${DURATION}s" \
        --csv=$RESULTS_DIR/run_${i}_phase_a \
        --only-summary
        
    echo "   [STATUS] Phase A complete. Waiting ${COOLDOWN}s cooldown..."
    sleep $COOLDOWN
    
    # ── PHASE B: Load ─────────────────────────────────────────
    # We use 100 users to hit the system hard
    echo "   [PHASE B] Starting Load (100 users)..."
    locust -f tests/performance/locustfile_scenario1.py \
        --headless \
        --users 100 \
        --spawn-rate 20 \
        --host $TARGET_URL \
        --run-time "${DURATION}s" \
        --csv=$RESULTS_DIR/run_${i}_phase_b \
        --only-summary
        
    echo "   [STATUS] Phase B complete. Iteration $i finished."
    
    if [ $i -lt $ITERATIONS ]; then
        echo "   [COOLDOWN] Waiting ${COOLDOWN}s before next run..."
        sleep $COOLDOWN
    fi
done

echo ""
echo "============================================================"
echo " 📊 [AGGREGATION] Computing Performance Metrics Table"
echo "============================================================"
# Point 2: Aggregation for p50/p95/p99 (ensured)
python3 scripts/aggregate.py $RESULTS_DIR

echo "------------------------------------------------------------"
echo " ✅ Scenario 1 Demo Finished. Results saved to $RESULTS_DIR"
echo "============================================================"
