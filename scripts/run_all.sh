#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# run_all.sh — Run all AIOps scenarios sequentially
# ═══════════════════════════════════════════════════════════════════════════════
#
# MỤC ĐÍCH:
#   Chạy tất cả kịch bản đánh giá hiệu năng AIOps
#
# KỊCH BẢN:
#   1. throughput: Baseline vs Load Comparison
#   2. cpu: CPU Stress Auto-Remediation (MTTR)
#   3. memory: Memory Exhaustion & DDoS Trade-off
#
# ĐẦU RA:
#   results/
#   ├── throughput/
#   │   ├── summary.json, comparison.json, results.csv
#   ├── cpu/
#   │   ├── summary.json, results.csv
#   ├── memory/
#   │   ├── summary.json, results.csv
#   └── all_scenarios.json    # Combined JSON output
#
# CÁCH DÙNG:
#   ./scripts/run_all.sh                    # Run all scenarios
#   ./scripts/run_all.sh --scenario cpu    # Run specific scenario only
#   ./scripts/run_all.sh --iterations 3   # Custom iterations
# ═══════════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Parse arguments
SCENARIO="all"
ITERATIONS=""
DURATION=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --scenario)
            SCENARIO="$2"
            shift 2
            ;;
        --iterations)
            ITERATIONS="--iterations $2"
            shift 2
            ;;
        --duration)
            DURATION="--duration $2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--scenario NAME] [--iterations N] [--duration S]"
            echo "  Scenarios: all, throughput, cpu, memory"
            exit 1
            ;;
    esac
done

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║  AIOps Performance Evaluation - Full Test Suite                             ║"
echo "╠══════════════════════════════════════════════════════════════════════════════╣"
echo "║  Scenario: $SCENARIO"
echo "║  Iterations: ${ITERATIONS:-default (3)}"
echo "║  Duration: ${DURATION:-default (300s)}"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"

cd "$ROOT_DIR"

# Run demo_runner.py with all scenarios
python scripts/demo_runner.py \
    --scenario "$SCENARIO" \
    --json-output \
    $ITERATIONS \
    $DURATION

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║  All scenarios completed!                                                     ║"
echo "║                                                                              ║"
echo "║  Results directory: results/                                                  ║"
echo "║    - results/all_scenarios.json    (combined output)                        ║"
echo "║    - results/throughput/           (scenario 1)                              ║"
echo "║    - results/cpu/                  (scenario 2)                              ║"
echo "║    - results/memory/                (scenario 3)                              ║"
echo "║                                                                              ║"
echo "║  Quick summary:                                                               ║"
echo "║    cat results/throughput/comparison.json                                    ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
