#!/bin/bash
# =============================================================
# stress.sh — Script chạy các kịch bản stress test
# =============================================================
# Cách dùng:
#   chmod +x stress.sh
#   ./stress.sh [scenario]
#
# Các scenario:
#   ./stress.sh overhead   → Kịch bản 1: đo overhead AIOps
#   ./stress.sh cpu        → Kịch bản 3: CPU stress
#   ./stress.sh memory     → Kịch bản 3 variant: memory stress
#   ./stress.sh all        → Chạy tuần tự tất cả
# =============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
ok()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn(){ echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERR]${NC} $1"; }

AGENT_URL="http://localhost:8080"
GRAFANA_URL="http://localhost:3000"
TARGET_CONTAINER="target-app"

# ── Kiểm tra hệ thống đang chạy ─────────────────────────────
check_system() {
    log "Kiểm tra hệ thống..."
    if ! docker compose ps | grep -q "running"; then
        err "Docker Compose chưa chạy! Chạy: docker compose up -d"
        exit 1
    fi
    if ! curl -s "$AGENT_URL/health" > /dev/null; then
        err "Agent chưa sẵn sàng tại $AGENT_URL"
        exit 1
    fi
    ok "Hệ thống sẵn sàng"
}

# ── Kịch bản 1: Đo Overhead ─────────────────────────────────
scenario_overhead() {
    log "=== KỊCH BẢN 1: Đo Overhead AIOps ==="
    log "Bước 1: Tắt Agent, đo baseline 2 phút..."
    docker compose stop agent
    log "Agent đã tắt. Đang đo baseline..."
    log ">>> Mở Grafana $GRAFANA_URL và xuất metrics CPU/RAM/Network"
    sleep 120
    
    log "Bước 2: Bật Agent, đo với AIOps 2 phút..."
    docker compose start agent
    sleep 5
    ok "Agent đã bật."
    log ">>> Đo lại trong Grafana — so sánh delta CPU/RAM"
    sleep 120
    
    ok "Kịch bản 1 hoàn thành. So sánh 2 khoảng thời gian trên Grafana."
}

# ── Kịch bản 3a: CPU Stress ─────────────────────────────────
scenario_cpu() {
    log "=== KỊCH BẢN 3: CPU Stress ==="
    log "Ghi timestamp bắt đầu: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log "Chạy stress-ng trong container $TARGET_CONTAINER (90 giây)..."
    
    docker exec "$TARGET_CONTAINER" stress-ng \
        --cpu 4 \
        --timeout 90s \
        --metrics-brief &
    
    STRESS_PID=$!
    log "stress-ng PID: $STRESS_PID"
    log "Chờ AlertManager phát hiện và Agent can thiệp..."
    log "Theo dõi: curl $AGENT_URL/logs | python3 -m json.tool"
    
    wait $STRESS_PID
    log "stress-ng kết thúc. Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    
    sleep 30
    log "Lấy action log của Agent:"
    curl -s "$AGENT_URL/logs?limit=5" | python3 -m json.tool 2>/dev/null || \
        curl -s "$AGENT_URL/logs?limit=5"
    
    ok "Kịch bản 3 hoàn thành."
}

# ── Kịch bản 3b: Memory Stress ──────────────────────────────
scenario_memory() {
    log "=== KỊCH BẢN 3b: Memory Stress ==="
    log "Chạy stress-ng memory trong $TARGET_CONTAINER (60 giây)..."
    
    docker exec "$TARGET_CONTAINER" stress-ng \
        --vm 2 \
        --vm-bytes 256M \
        --timeout 60s \
        --metrics-brief
    
    ok "Memory stress kết thúc."
}

# ── Main ─────────────────────────────────────────────────────
case "${1:-help}" in
    overhead)
        check_system
        scenario_overhead
        ;;
    cpu)
        check_system
        scenario_cpu
        ;;
    memory)
        check_system
        scenario_memory
        ;;
    all)
        check_system
        scenario_overhead
        echo ""
        warn "Nghỉ 60s giữa các kịch bản..."
        sleep 60
        scenario_cpu
        echo ""
        warn "Nghỉ 60s..."
        sleep 60
        scenario_memory
        ok "Tất cả kịch bản hoàn thành!"
        ;;
    *)
        echo "Cách dùng: $0 [overhead|cpu|memory|all]"
        echo ""
        echo "  overhead  Kịch bản 1: Đo overhead của hệ thống AIOps"
        echo "  cpu       Kịch bản 3: CPU stress → Agent tự kill process"
        echo "  memory    Kịch bản 3b: Memory stress"
        echo "  all       Chạy tuần tự tất cả"
        ;;
esac
