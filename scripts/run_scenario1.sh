#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# run_scenario1.sh — Thin wrapper for demo_runner.py (Throughput scenario)
# ═══════════════════════════════════════════════════════════════════════════════
#
# MỤC ĐÍCH:
#   Chạy kịch bản 1: Baseline vs Load Comparison
#   Đánh giá hiệu năng hệ thống dưới tải bình thường và tấn công DDoS.
#
# ĐẦU RA:
#   results/throughput/
#   ├── runs/
#   │   ├── run_001/
#   │   │   ├── baseline_metrics.json
#   │   │   └── load_metrics.json
#   │   ├── run_002/
#   │   └── run_003/
#   ├── summary.json         # Aggregated stats
#   ├── comparison.json     # Baseline vs Load comparison
#   └── results.csv         # CSV export
#
# CÁCH DÙNG:
#   ./scripts/run_scenario1.sh                    # Default: 3 iterations
#   ./scripts/run_scenario1.sh --iterations 5     # Custom iterations
#   ./scripts/run_scenario1.sh --duration 600     # Custom duration (seconds)
#
# KIỂM TRA KẾT QUẢ:
#   cat results/throughput/summary.json
#   cat results/throughput/comparison.json
# ═══════════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$ROOT_DIR/results/throughput"

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║  DEMO: Kịch bản 1 - Throughput & Latency Baseline vs Load Comparison       ║"
echo "╠══════════════════════════════════════════════════════════════════════════════╣"
echo "║  Mục tiêu:                                                                    ║"
echo "║    - So sánh latency dưới tải 1 user (baseline) vs 100 users (load)          ║"
echo "║    - Xác định breaking point của hệ thống                                  ║"
echo "║    - Đo throughput và error rate                                             ║"
echo "║                                                                              ║"
echo "║  Phases:                                                                      ║"
echo "║    Phase 1 (baseline): 20 users, ổn định — đo performance nền              ║"
echo "║    Phase 2 (load): 50→500 users, staged — đo degradation                    ║"
echo "║                                                                              ║"
echo "║  Baseline comparison:                                                        ║"
echo "║    Pass criteria: Load p95 < 3x Baseline p95                                 ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"

# Parse arguments
ITERATIONS=""
DURATION=""
while [[ $# -gt 0 ]]; do
    case $1 in
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
            echo "Usage: $0 [--iterations N] [--duration S]"
            exit 1
            ;;
    esac
done

# Create results directory
mkdir -p "$RESULTS_DIR"

# Run demo_runner.py
cd "$ROOT_DIR"
python scripts/demo_runner.py \
    --scenario throughput \
    --json-output \
    --results-dir "$RESULTS_DIR" \
    $ITERATIONS \
    $DURATION

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║  Kết quả đã được lưu vào:                                                      ║"
echo "║    $RESULTS_DIR/summary.json                                                  ║"
echo "║    $RESULTS_DIR/comparison.json                                                ║"
echo "║    $RESULTS_DIR/results.csv                                                     ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
