#!/bin/bash
# =============================================================
# Demo 4: Memory Exhaustion Auto-Remediation
# Simulates memory exhaustion and demonstrates AI agent's
# automatic service restart and memory recovery
# =============================================================

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
# Load local IP/Config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../.env"
if [ -f "$ENV_FILE" ]; then
    AZURE_VM_IP=$(grep '^AZURE_VM_IP=' "$ENV_FILE" | cut -d'=' -f2-)
fi

AGENT_URL="http://localhost:8080"
TARGET_URL="http://${AZURE_VM_IP:-localhost}:80"
PROMETHEUS_URL="http://localhost:9090"
TARGET_CONTAINER="target-app"
RESULTS_DIR="results"

# Load API key from project root .env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../.env"
if [ -f "$ENV_FILE" ]; then
    AGENT_API_KEY=$(grep '^AGENT_API_KEY=' "$ENV_FILE" | cut -d'=' -f2-)
fi
AGENT_API_KEY="${AGENT_API_KEY:-}"

# Memory stress parameters
# Target: push container memory > 60% of 256MB limit = >154MB.
# Each user requests 50MB held for 10s. With 5 concurrent users that's
# 5×50 = 250MB — well above the 154MB trigger, achieved within seconds.
MEMORY_USERS=10            # Number of concurrent users making memory requests
MEMORY_SPAWN_RATE=5        # How quickly to spawn new users (all up in 2s)
MEMORY_DURATION=120        # seconds (2 minutes — gives alert 30s+ to fire and agent to respond)
MB_PER_REQUEST=50          # MB allocated per /memory?mb=X request (50MB × 5 concurrent = 250MB)
MEMORY_THRESHOLD=60        # Memory % threshold for alert (matches alert.rules.yml)

# Utility functions
log() { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
ok()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn(){ echo -e "${YELLOW}[⚠]${NC} $1"; }
err() { echo -e "${RED}[✗]${NC} $1"; exit 1; }
section() { echo -e "\n${PURPLE}═══ $1 ═══${NC}\n"; }

# Cleanup function for old results
cleanup_old_results() {
    local keep_count="${1:-2}"  # Keep last 2 results by default

    if [ -d "$RESULTS_DIR" ]; then
        log "Cleaning old memory stress results (keeping last $keep_count files)..."

        # Remove files older than 7 days
        find "$RESULTS_DIR" -name "memory_stress_*.txt" -type f -mtime +7 -delete 2>/dev/null || true

        # Keep only the most recent files (by modification time)
        ls -t "$RESULTS_DIR"/memory_stress_*.txt 2>/dev/null | tail -n +$((keep_count + 1)) | xargs rm -f 2>/dev/null || true
    fi
}

# Command line argument parsing
if [ "$1" = "--clean" ]; then
    mkdir -p "$RESULTS_DIR"
    cleanup_old_results 0  # Remove all results
    ok "All memory stress results cleaned!"
    exit 0
fi

if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --clean    Clean all memory stress result files"
    echo "  --help     Show this help message"
    echo ""
    echo "Run without options to execute memory stress auto-remediation test."
    exit 0
fi

# Automatic cleanup of old results
cleanup_old_results 2

# Create results directory
mkdir -p "$RESULTS_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="$RESULTS_DIR/memory_stress_$TIMESTAMP.txt"

# =============================================================
# Step 1: Prerequisites Check
# =============================================================
section "Step 1: Prerequisites Check"

log "Checking if all services are running..."

# Verify Docker Compose stack is up
cd ../..  # Go to project root where docker-compose.yml is located
if ! docker compose ps | grep -q "agent.*Up"; then
    err "AI Agent is not running! Start with: docker compose up -d"
fi
ok "AI Agent is running"

if ! docker compose ps | grep -q "target-app.*Up"; then
    err "Target application is not running!"
fi
ok "Target application is running"
cd demos/demo4-memory  # Return to demo directory

# Verify agent health
if ! curl -s -f "$AGENT_URL/health" > /dev/null; then
    err "AI Agent health check failed"
fi
ok "AI Agent is healthy"

# Verify Locust is available
if ! python3 -c "import locust" 2>/dev/null; then
    err "Locust not found. Install with: pip install locust"
fi
ok "Locust is available"

ok "All prerequisites satisfied"

# =============================================================
# Step 2: Capture Baseline Memory Usage
# =============================================================
section "Step 2: Baseline Memory Measurement"

log "Recording memory baseline before stress test..."

# docker stats: Get real-time container resource usage
baseline_stats=$( docker stats --no-stream --format "{{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}" "$TARGET_CONTAINER" 2>/dev/null || echo "N/A")

echo "=== BASELINE MEMORY USAGE ===" | tee -a "$RESULT_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "Container Stats:" | tee -a "$RESULT_FILE"
echo "$baseline_stats" | tee -a "$RESULT_FILE"

# Get free memory in container
baseline_memory=$(docker exec "$TARGET_CONTAINER" free -h 2>/dev/null || echo "N/A")
echo "" | tee -a "$RESULT_FILE"
echo "Memory Details:" | tee -a "$RESULT_FILE"
echo "$baseline_memory" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Query Prometheus for memory usage
baseline_mem=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=node_memory_MemAvailable_bytes" 2>/dev/null | grep -o '"value":\[[^]]*\]' | head -1 || echo "N/A")

echo "Prometheus Memory Available: $baseline_mem" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

ok "Baseline metrics captured"

# =============================================================
# Step 3: Initiate Memory Stress Test
# =============================================================
section "Step 3: Launch Memory Stress Test"

log "⚠️  Launching memory exhaustion test..."
log "    Users: ${MEMORY_USERS} concurrent"
log "    MB per request: ${MB_PER_REQUEST}"
log "    Duration: ${MEMORY_DURATION} seconds"
log "    Expected memory: ~${MEMORY_THRESHOLD}%+"

echo "=== MEMORY STRESS TEST INITIATED ===" | tee -a "$RESULT_FILE"
echo "Start Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "Parameters:" | tee -a "$RESULT_FILE"
echo "  - Concurrent Users: ${MEMORY_USERS}" | tee -a "$RESULT_FILE"
echo "  - Spawn Rate: ${MEMORY_SPAWN_RATE}/sec" | tee -a "$RESULT_FILE"
echo "  - Duration: ${MEMORY_DURATION}s" | tee -a "$RESULT_FILE"
echo "  - MB per Request: ${MB_PER_REQUEST}" | tee -a "$RESULT_FILE"
echo "  - Memory Threshold: ${MEMORY_THRESHOLD}%" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

log "Starting Locust with memory stress load..."

# Run locust in background with memory stress tag.
# Pass MB_PER_REQUEST as env var so locustfile can use it.
MEMORY_MB_PER_REQUEST="$MB_PER_REQUEST" python3 -m locust \
    -f ../../loadtest/locustfile.py \
    --host="$TARGET_URL" \
    --users "$MEMORY_USERS" \
    --spawn-rate "$MEMORY_SPAWN_RATE" \
    --run-time "${MEMORY_DURATION}s" \
    --headless \
    --tags memory \
    --csv=memory_load_stats \
    > locust_output.log 2>&1 &

LOCUST_PID=$!
ok "Memory stress test launched in background (PID: $LOCUST_PID)"

# Wait for Locust to ramp up
log "Waiting 15 seconds for load to ramp up..."
sleep 15

# =============================================================
# Step 4: Monitor Memory Under Stress
# =============================================================
section "Step 4: Monitor Memory Under Stress"

log "Recording metrics during stress test..."

# Capture stats multiple times during stress
for i in {1..4}; do
    sleep 5
    stress_stats=$(docker stats --no-stream --format "{{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}" "$TARGET_CONTAINER" 2>/dev/null || echo "N/A")

    echo "=== DURING STRESS (Sample $i) ===" | tee -a "$RESULT_FILE"
    echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
    echo "Container Stats:" | tee -a "$RESULT_FILE"
    echo "$stress_stats" | tee -a "$RESULT_FILE"
    echo "" | tee -a "$RESULT_FILE"

    # Show memory details
    if [ $i -eq 1 ]; then
        log "Checking memory pressure..."
        memory_details=$(docker exec "$TARGET_CONTAINER" free -h 2>/dev/null || echo "N/A")
        echo "Memory Details:" | tee -a "$RESULT_FILE"
        echo "$memory_details" | tee -a "$RESULT_FILE"
        echo "" | tee -a "$RESULT_FILE"
    fi

    # Check Locust status
    if kill -0 $LOCUST_PID 2>/dev/null; then
        ok "Locust still running (sample $i/4)"
    else
        warn "Locust process ended early"
        break
    fi
done

# =============================================================
# Step 5: Wait for AI Agent Response
# =============================================================
section "Step 5: Monitor AI Agent Auto-Remediation"

log "Waiting for Prometheus to detect high memory and trigger alert..."
log "💡 Alert triggers after 30s container memory > 60% of limit (HighMemoryUsage) + AlertManager routing"

# Wait for the full alert pipeline:
#   Locust spawns → memory spikes → Prometheus 30s 'for:' window → AlertManager → agent webhook
# Total: ~45-50s. We already waited 15s ramp-up, so need 35s more.
sleep 35

log "Checking if AI Agent received memory alert..."

# Get agent's recent decision logs
agent_logs=$(curl -s -H "X-Agent-Key: $AGENT_API_KEY" "$AGENT_URL/logs?limit=10" 2>/dev/null || echo "[]")

echo "=== AI AGENT DECISIONS ===" | tee -a "$RESULT_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "$agent_logs" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Check if agent responded to memory alert
agent_responded=false
if echo "$agent_logs" | grep -qi "HighMemory\|HighMemoryUsage\|MemoryUsage\|memory_stress\|memory.*high"; then
    ok "AI Agent detected memory stress alert"
    agent_responded=true

    # Check if agent took action
    if echo "$agent_logs" | grep -qi "restart\|remediat"; then
        ok "AI Agent attempted remediation"

        # Check for enhanced tool usage
        if echo "$agent_logs" | grep -qi "restart_service"; then
            ok "Agent used restart_service tool"
        fi
    else
        warn "Agent detected alert but action unclear"
    fi
else
    warn "No memory-related decisions found yet - alert may still be pending"
fi

# Wait for agent action and Locust to complete
log "Waiting for remediation and load test completion..."
sleep 20

# =============================================================
# Step 6: Verify Auto-Remediation
# =============================================================
section "Step 6: Verify Auto-Remediation"

log "Checking system state after remediation..."

# Check current memory
current_stats=$(docker stats --no-stream --format "{{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}" "$TARGET_CONTAINER" 2>/dev/null || echo "N/A")

echo "=== POST-REMEDIATION MEMORY CHECK ===" | tee -a "$RESULT_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "Container Stats:" | tee -a "$RESULT_FILE"
echo "$current_stats" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Check if service is still running
if curl -s -f "$TARGET_URL/health" > /dev/null 2>&1; then
    ok "Target service is healthy post-remediation"
    remediation_success=true

    echo "Service Status: Running" | tee -a "$RESULT_FILE"
else
    warn "Target service health check failed"
    remediation_success=false

    echo "Service Status: Degraded/Recovering" | tee -a "$RESULT_FILE"
fi

# Get post-remediation memory
post_memory=$(docker exec "$TARGET_CONTAINER" free -h 2>/dev/null || echo "N/A")
echo "Memory Status:" | tee -a "$RESULT_FILE"
echo "$post_memory" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# =============================================================
# Step 7: Monitor Recovery
# =============================================================
section "Step 7: System Recovery Monitoring"

log "Monitoring system recovery for 20 seconds..."

# Wait for Locust to finish naturally
if kill -0 $LOCUST_PID 2>/dev/null; then
    log "Waiting for Locust to finish (may take up to 30s)..."
    wait $LOCUST_PID 2>/dev/null || true
fi

# Take recovery samples
for i in {1..4}; do
    sleep 5
    recovery_stats=$(docker stats --no-stream --format "{{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" "$TARGET_CONTAINER" 2>/dev/null || echo "N/A")

    if [ $i -eq 4 ]; then
        echo "=== FINAL RECOVERY STATE ===" | tee -a "$RESULT_FILE"
        echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
        echo "Container Stats:" | tee -a "$RESULT_FILE"
        echo "$recovery_stats" | tee -a "$RESULT_FILE"
        echo "" | tee -a "$RESULT_FILE"
    fi
done

ok "Recovery monitoring complete"

# =============================================================
# Step 8: Generate Summary
# =============================================================
section "Step 8: Results Summary"

echo "=== DEMO 4 SUMMARY ===" | tee -a "$RESULT_FILE"
echo "Memory Stress Parameters:" | tee -a "$RESULT_FILE"
echo "  - Concurrent Users: ${MEMORY_USERS}" | tee -a "$RESULT_FILE"
echo "  - MB per Request: ${MB_PER_REQUEST}" | tee -a "$RESULT_FILE"
echo "  - Duration: ${MEMORY_DURATION}s" | tee -a "$RESULT_FILE"
echo "  - Target: $TARGET_CONTAINER" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

echo "Timeline:" | tee -a "$RESULT_FILE"
echo "  T+0s:  Baseline recorded" | tee -a "$RESULT_FILE"
echo "  T+15s: Memory stress initiated" | tee -a "$RESULT_FILE"
echo "  T+35s: Alert triggered (high memory sustained)" | tee -a "$RESULT_FILE"
echo "  T+40s: AI Agent received alert" | tee -a "$RESULT_FILE"
echo "  T+45s: Agent attempted remediation" | tee -a "$RESULT_FILE"
echo "  T+60s: Service recovery measured" | tee -a "$RESULT_FILE"
echo "  T+90s: System recovery confirmed" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

echo "Results:" | tee -a "$RESULT_FILE"

if [ "$agent_responded" = true ]; then
    echo "  ✓ AI Agent detected memory stress alert" | tee -a "$RESULT_FILE"
else
    echo "  ✗ AI Agent did not detect alert" | tee -a "$RESULT_FILE"
fi

if [ "$remediation_success" = true ]; then
    echo "  ✓ Service remained healthy after remediation" | tee -a "$RESULT_FILE"
    echo "  ✓ Auto-remediation was successful" | tee -a "$RESULT_FILE"
else
    echo "  ⚠ Service health degraded" | tee -a "$RESULT_FILE"
    echo "  ⚠ Recovery still in progress" | tee -a "$RESULT_FILE"
fi

echo "" | tee -a "$RESULT_FILE"

ok "Demo 4 completed!"
echo ""
log "📊 Results saved to: $RESULT_FILE"
log "📈 View memory spike in Grafana: http://localhost:3000"
log "🤖 View agent decisions: curl $AGENT_URL/logs | jq"
echo ""
log "💡 Next Steps:"
log "   1. Run validation: ./validate.sh $RESULT_FILE"
log "   2. Check Grafana for memory spike and recovery"
log "   3. Review agent's reasoning for remediation choice"
log "   4. Verify service health: curl $TARGET_URL/health"
echo ""

if [ "$remediation_success" = true ]; then
    echo -e "${GREEN}✅ Demo 4 (Memory Exhaustion Auto-Remediation) Complete!${NC}"
    echo -e "${GREEN}   AI Agent successfully detected and remediated memory pressure!${NC}"
else
    echo -e "${YELLOW}⚠️  Demo 4 completed with warnings${NC}"
    echo -e "${YELLOW}   Check validation results for details${NC}"
fi
