#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# run_scenario2.sh — Thin wrapper for demo_runner.py (CPU Remediation MTTR)
# ═══════════════════════════════════════════════════════════════════════════════
#
# MỤC ĐÍCH:
#   Chạy kịch bản 2: CPU Stress Auto-Remediation
#   So sánh MTTR giữa AI Agent và Rule-Based Agent
#
# ĐẦU RA:
#   results/cpu/
#   ├── runs/
#   │   ├── run_001/
#   │   │   └── remediation_metrics.json
#   │   ├── run_002/
#   │   └── run_003/
#   ├── summary.json         # Aggregated MTTR stats
#   └── results.csv         # CSV export
#
# CÁCH DÙNG:
#   ./scripts/run_scenario2.sh                    # Default: 3 iterations
#   ./scripts/run_scenario2.sh --iterations 5     # Custom iterations
#
# KẾT QUẢ MTTR:
#   - detection_s: Thời gian phát hiện (T1 - T0)
#   - response_s: Thời gian phản hồi (T2 - T1)
#   - remediation_s: Thời gian khắc phục (T3 - T2)
#   - mttr_s: Mean Time To Recovery tổng thể (T3 - T0)
# ═══════════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$ROOT_DIR/results/cpu"

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║  DEMO: Kịch bản 2 - CPU Stress Auto-Remediation (MTTR)                     ║"
echo "╠══════════════════════════════════════════════════════════════════════════════╣"
echo "║  Mục tiêu:                                                                    ║"
echo "║    - Đo MTTR (Mean Time To Recovery) cho sự cố CPU stress                   ║"
echo "║    - So sánh AI Agent vs Rule-Based Agent                                    ║"
echo "║    - Phân tích: detection + response + remediation time                     ║"
echo "║                                                                              ║"
echo "║  Injection:                                                                   ║"
echo "║    stress-ng --cpu 4 --timeout {duration}s                                   ║"
echo "║                                                                              ║"
echo "║  Recovery criteria:                                                           ║"
echo "║    CPU% < 30% for 3 consecutive polls                                        ║"
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
    --scenario cpu \
    --json-output \
    --results-dir "$RESULTS_DIR" \
    $ITERATIONS

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║  Kết quả đã được lưu vào:                                                      ║"
echo "║    $RESULTS_DIR/summary.json                                                  ║"
echo "║    $RESULTS_DIR/results.csv                                                   ║"
echo "║                                                                              ║"
echo "║  Để so sánh AI vs Rule-Based Agent, chạy với --agent-url khác nhau:         ║"
echo "║    python scripts/demo_runner.py --scenario cpu --agent-url http://:8080     ║"
echo "║    python scripts/demo_runner.py --scenario cpu --agent-url http://:5001     ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
