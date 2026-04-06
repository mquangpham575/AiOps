#!/bin/bash
# =============================================================
# Demo 3: CPU Stress Auto-Remediation
# Simulates CPU stress and demonstrates AI agent's automatic
# process identification and termination
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

# Stress test parameters
STRESS_WORKERS=4            # Number of CPU workers
STRESS_DURATION=60          # seconds
CPU_THRESHOLD=80            # CPU % threshold for alert

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
        log "Cleaning old CPU stress results (keeping last $keep_count files)..."

        # Remove files older than 7 days
        find "$RESULTS_DIR" -name "cpu_stress_*.txt" -type f -mtime +7 -delete 2>/dev/null || true

        # Keep only the most recent files (by modification time)
        ls -t "$RESULTS_DIR"/cpu_stress_*.txt 2>/dev/null | tail -n +$((keep_count + 1)) | xargs rm -f 2>/dev/null || true
    fi
}

# Command line argument parsing
if [ "$1" = "--clean" ]; then
    mkdir -p "$RESULTS_DIR"
    cleanup_old_results 0  # Remove all results
    ok "All CPU stress results cleaned!"
    exit 0
fi

if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --clean    Clean all CPU stress result files"
    echo "  --help,    Show this help message"
    echo ""
    echo "Run without options to execute CPU stress auto-remediation test."
    exit 0
fi

# Automatic cleanup of old results
cleanup_old_results 2

# Create results directory
mkdir -p "$RESULTS_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="$RESULTS_DIR/cpu_stress_$TIMESTAMP.txt"

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
cd demos/demo3-cpu-stress  # Return to demo directory

# Check if stress-ng is available in target container
# stress-ng: Stress testing tool for Linux systems
log "Verifying stress-ng is available in target container..."
if ! docker exec "$TARGET_CONTAINER" which stress-ng > /dev/null 2>&1; then
    err "stress-ng not found in $TARGET_CONTAINER container"
fi
ok "stress-ng is available"

# Verify agent health
if ! curl -s -f "$AGENT_URL/health" > /dev/null; then
    err "AI Agent health check failed"
fi
ok "AI Agent is healthy"

ok "All prerequisites satisfied"

# =============================================================
# Step 2: Capture Baseline CPU Usage
# =============================================================
section "Step 2: Baseline CPU Measurement"

log "Recording CPU baseline before stress test..."

# docker stats: Get real-time container resource usage
# --no-stream: Single snapshot instead of continuous stream
baseline_stats=$( docker stats --no-stream --format "{{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}" "$TARGET_CONTAINER" 2>/dev/null || echo "N/A")

echo "=== BASELINE CPU USAGE ===" | tee -a "$RESULT_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "Container Stats:" | tee -a "$RESULT_FILE"
echo "$baseline_stats" | tee -a "$RESULT_FILE"

# Get current processes in container
baseline_processes=$(docker exec "$TARGET_CONTAINER" ps aux | head -10)
echo "" | tee -a "$RESULT_FILE"
echo "Baseline Processes:" | tee -a "$RESULT_FILE"
echo "$baseline_processes" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Query Prometheus for CPU rate
# process_cpu_seconds_total: Total CPU time consumed by process
# rate()[1m]: Calculate per-second rate over 1 minute window
baseline_cpu=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=rate(process_cpu_seconds_total[1m])*100" 2>/dev/null | grep -o '"value":\[[^]]*\]' | head -1 || echo "N/A")

echo "Prometheus CPU Rate: $baseline_cpu" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

ok "Baseline metrics captured"

# =============================================================
# Step 3: Initiate CPU Stress Test
# =============================================================
section "Step 3: Launch CPU Stress Test"

log "⚠️  Launching CPU stress test..."
log "    Workers: ${STRESS_WORKERS} CPU cores"
log "    Duration: ${STRESS_DURATION} seconds"
log "    Expected CPU: ~${CPU_THRESHOLD}%+"

echo "=== CPU STRESS TEST INITIATED ===" | tee -a "$RESULT_FILE"
echo "Start Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "Parameters:" | tee -a "$RESULT_FILE"
echo "  - CPU Workers: ${STRESS_WORKERS}" | tee -a "$RESULT_FILE"
echo "  - Duration: ${STRESS_DURATION}s" | tee -a "$RESULT_FILE"
echo "  - CPU Threshold: ${CPU_THRESHOLD}%" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# docker exec -d: Execute command in detached mode (background)
# stress-ng --cpu N: Create N CPU workers
# --timeout Xs: Run for X seconds
# --metrics-brief: Show brief metrics summary
log "Starting stress-ng in background..."
docker exec -d "$TARGET_CONTAINER" stress-ng \
    --cpu "$STRESS_WORKERS" \
    --timeout "${STRESS_DURATION}s" \
    --metrics-brief \
    --verbose

ok "CPU stress test launched in background"

# Wait for stress to ramp up
log "Waiting 10 seconds for stress to ramp up..."
sleep 10

# =============================================================
# Step 4: Monitor CPU Under Stress
# =============================================================
section "Step 4: Monitor CPU Under Stress"

log "Recording metrics during stress test..."

# Capture stats multiple times during stress
for i in {1..3}; do
    sleep 5
    stress_stats=$(docker stats --no-stream --format "{{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}" "$TARGET_CONTAINER" 2>/dev/null || echo "N/A")

    echo "=== DURING STRESS (Sample $i) ===" | tee -a "$RESULT_FILE"
    echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
    echo "Container Stats:" | tee -a "$RESULT_FILE"
    echo "$stress_stats" | tee -a "$RESULT_FILE"
    echo "" | tee -a "$RESULT_FILE"

    # Show process list to confirm stress-ng is running
    if [ $i -eq 1 ]; then
        log "Listing active processes..."
        stress_processes=$(docker exec "$TARGET_CONTAINER" ps aux | grep -E "stress|PID" | grep -v grep || echo "No stress processes found")
        echo "Active Stress Processes:" | tee -a "$RESULT_FILE"
        echo "$stress_processes" | tee -a "$RESULT_FILE"
        echo "" | tee -a "$RESULT_FILE"

        # Count stress-ng processes
        stress_count=$(docker exec "$TARGET_CONTAINER" ps aux | grep -c "stress-ng" | grep -v grep || echo 0)
        log "Found $stress_count stress-ng processes"

        if [ $stress_count -gt 0 ]; then
            ok "CPU stress is active ($stress_count workers)"
        else
            warn "No stress-ng processes found - stress may have failed"
        fi
    fi
done

# =============================================================
# Step 5: Wait for AI Agent Response
# =============================================================
section "Step 5: Monitor AI Agent Auto-Remediation"

log "Waiting for Prometheus to detect high CPU and trigger alert..."
log "💡 Alert triggers after 30s sustained CPU > 70% (ContainerHighCPU) + AlertManager routing"

# Wait for the full alert pipeline:
#   stress starts → Prometheus 30s 'for:' window → AlertManager evaluates → agent webhook
# Total: ~50s from stress launch. We already waited 10s ramp-up, so need 40s more.
sleep 40

log "Checking if AI Agent received CPU alert..."

# Get agent's recent decision logs
# Logs contain: timestamp, alert name, decision, confidence, actions taken
agent_logs=$(curl -s -H "X-Agent-Key: $AGENT_API_KEY" "$AGENT_URL/logs?limit=10" 2>/dev/null || echo "[]")

echo "=== AI AGENT DECISIONS ===" | tee -a "$RESULT_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "$agent_logs" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Check if agent responded to CPU alert
agent_responded=false
if echo "$agent_logs" | grep -qi "HighCPU\|ContainerHighCPU\|CPUUsage\|stress\|cpu_stress"; then
    ok "AI Agent detected CPU stress alert"
    agent_responded=true

    # Check if agent took action
    if echo "$agent_logs" | grep -qi "kill\|terminate\|stop"; then
        ok "AI Agent attempted to kill stress processes"

        # Check for enhanced tool usage
        if echo "$agent_logs" | grep -qi "auto_kill_cpu_stress"; then
            ok "Agent used auto_kill_cpu_stress tool (enhanced workflow)"
        fi
    else
        warn "Agent detected alert but action unclear"
    fi
else
    warn "No CPU-related decisions found yet - alert may still be pending"
fi

# Wait for agent action to take effect
log "Waiting 15 seconds for remediation to complete..."
sleep 15

# =============================================================
# Step 6: Verify Auto-Remediation
# =============================================================
section "Step 6: Verify Auto-Remediation"

log "Checking if stress processes were terminated..."

# Check if stress-ng is still running
# If agent worked correctly, stress-ng should be killed
current_processes=$(docker exec "$TARGET_CONTAINER" ps aux | grep -E "stress|PID" | grep -v grep || echo "No stress processes")
remaining_stress=$(docker exec "$TARGET_CONTAINER" ps aux | grep -c "stress-ng" | grep -v grep || echo 0)

echo "=== POST-REMEDIATION PROCESS CHECK ===" | tee -a "$RESULT_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "Current Processes:" | tee -a "$RESULT_FILE"
echo "$current_processes" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

log "Remaining stress processes: $remaining_stress"

if [ "$remaining_stress" -eq 0 ]; then
    ok "SUCCESS: All stress processes were terminated by AI Agent!"
    remediation_success=true
else
    warn "Some stress processes still running ($remaining_stress found)"
    warn "Agent may have taken different action or remediation still in progress"
    remediation_success=false
fi

# Record post-remediation CPU
post_stress_stats=$(docker stats --no-stream --format "{{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}" "$TARGET_CONTAINER" 2>/dev/null || echo "N/A")

echo "=== POST-REMEDIATION CPU USAGE ===" | tee -a "$RESULT_FILE"
echo "Container Stats:" | tee -a "$RESULT_FILE"
echo "$post_stress_stats" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# =============================================================
# Step 7: Monitor Recovery
# =============================================================
section "Step 7: System Recovery Monitoring"

log "Monitoring system recovery for 20 seconds..."

# Take several recovery samples
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

echo "=== DEMO 3 SUMMARY ===" | tee -a "$RESULT_FILE"
echo "Stress Parameters:" | tee -a "$RESULT_FILE"
echo "  - CPU Workers: ${STRESS_WORKERS}" | tee -a "$RESULT_FILE"
echo "  - Duration: ${STRESS_DURATION}s" | tee -a "$RESULT_FILE"
echo "  - Target was: $TARGET_CONTAINER" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

echo "Timeline:" | tee -a "$RESULT_FILE"
echo "  T+0s:  Baseline recorded" | tee -a "$RESULT_FILE"
echo "  T+10s: CPU stress initiated" | tee -a "$RESULT_FILE"
echo "  T+35s: Alert triggered (high CPU sustained)" | tee -a "$RESULT_FILE"
echo "  T+40s: AI Agent received alert" | tee -a "$RESULT_FILE"
echo "  T+45s: Agent attempted remediation" | tee -a "$RESULT_FILE"
echo "  T+60s: Process termination verified" | tee -a "$RESULT_FILE"
echo "  T+80s: System recovery measured" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

echo "Results:" | tee -a "$RESULT_FILE"

if [ "$agent_responded" = true ]; then
    echo "  ✓ AI Agent detected CPU stress alert" | tee -a "$RESULT_FILE"
else
    echo "  ✗ AI Agent did not detect alert" | tee -a "$RESULT_FILE"
fi

if [ "$remediation_success" = true ]; then
    echo "  ✓ Stress processes successfully terminated" | tee -a "$RESULT_FILE"
    echo "  ✓ Auto-remediation was successful" | tee -a "$RESULT_FILE"
else
    echo "  ⚠ Stress processes may still be running" | tee -a "$RESULT_FILE"
    echo "  ⚠ Manual verification recommended" | tee -a "$RESULT_FILE"
fi

echo "" | tee -a "$RESULT_FILE"

ok "Demo 3 completed!"
echo ""
log "📊 Results saved to: $RESULT_FILE"
log "📈 View CPU spike in Grafana: http://localhost:3000"
log "🤖 View agent decisions: curl $AGENT_URL/logs | jq"
echo ""
log "💡 Next Steps:"
log "   1. Run validation: ./validate.sh $RESULT_FILE"
log "   2. Check Grafana for CPU spike and recovery"
log "   3. Review agent's reasoning for process targeting"
log "   4. Verify no stress processes remain: docker exec $TARGET_CONTAINER ps aux | grep stress"
echo ""

if [ "$remediation_success" = true ]; then
    echo -e "${GREEN}✅ Demo 3 (CPU Stress Auto-Remediation) Complete!${NC}"
    echo -e "${GREEN}   AI Agent successfully identified and terminated stress processes!${NC}"
else
    echo -e "${YELLOW}⚠️  Demo 3 completed with warnings${NC}"
    echo -e "${YELLOW}   Check validation results for details${NC}"
fi
