#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# run_scenario3.sh — Thin wrapper for demo_runner.py (Memory/DDoS Trade-off)
# ═══════════════════════════════════════════════════════════════════════════════
#
# MỤC ĐÍCH:
#   Chạy kịch bản 3: Memory Exhaustion & DDoS Trade-off
#   Đánh giá hiệu quả rate limiting trong việc:
#     1. Block DDoS traffic
#     2. Không ảnh hưởng legitimate users
#
# ĐẦU RA:
#   results/memory/
#   ├── runs/
#   │   ├── run_001/
#   │   │   └── remediation_metrics.json
#   │   ├── run_002/
#   │   └── run_003/
#   ├── summary.json         # Aggregated stats
#   └── results.csv         # CSV export
#
# CÁCH DÙNG:
#   ./scripts/run_scenario3.sh                    # Default: 3 iterations
#   ./scripts/run_scenario3.sh --iterations 5     # Custom iterations
#
# USER CLASSES:
#   - LegitimateUser: Normal browsing, wait 1-2s (weight=1)
#   - AttackUser: Rapid flooding, wait 0.01-0.05s (weight=3)
#
# METRICS:
#   - legit_success_rate: Tỉ lệ request thành công của legitimate users
#   - attack_block_rate: Tỉ lệ attack bị block
#   - Trade-off: blocking vs collateral damage
# ═══════════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$ROOT_DIR/results/memory"

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║  DEMO: Kịch bản 3 - Memory Exhaustion & DDoS Trade-off Analysis            ║"
echo "╠══════════════════════════════════════════════════════════════════════════════╣"
echo "║  Mục tiêu:                                                                    ║"
echo "║    - Đánh giá hiệu quả của iptables rate limiting                           ║"
echo "║    - Block DDoS traffic: tỉ lệ attack bị chặn                              ║"
echo "║    - Collateral damage: tỉ lệ legitimate users bị ảnh hưởng                 ║"
echo "║    - Tìm optimal rate limit configuration                                   ║"
echo "║                                                                              ║"
echo "║  User Classes:                                                                ║"
echo "║    LegitimateUser: 1 user, wait 1-2s — represent real users                 ║"
echo "║    AttackUser: 3x weight, wait 0.01-0.05s — flood attack                    ║"
echo "║                                                                              ║"
echo "║  Test Configurations:                                                         ║"
echo "║    no_limit: Không có rate limit                                            ║"
echo "║    limit_100: Limit 100 req/s per IP                                        ║"
echo "║    limit_20: Limit 20 req/s per IP                                          ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"

# Parse arguments
ITERATIONS=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --iterations)
            ITERATIONS="--iterations $2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--iterations N]"
            exit 1
            ;;
    esac
done

# Create results directory
mkdir -p "$RESULTS_DIR"

# Run demo_runner.py
cd "$ROOT_DIR"
python scripts/demo_runner.py \
    --scenario memory \
    --json-output \
    --results-dir "$RESULTS_DIR" \
    $ITERATIONS

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║  Kết quả đã được lưu vào:                                                      ║"
echo "║    $RESULTS_DIR/summary.json                                                  ║"
echo "║    $RESULTS_DIR/results.csv                                                   ║"
echo "║                                                                              ║"
echo "║  Rate Limit Scripts:                                                          ║"
echo "║    ./scripts/set_rate_limit.sh --limit 100    # Limit 100 req/s              ║"
echo "║    ./scripts/set_rate_limit.sh --limit 20    # Limit 20 req/s               ║"
echo "║    ./scripts/set_rate_limit.sh --clear       # Clear all limits             ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
