#!/bin/bash
# =============================================================
# Demo 1: Baseline Performance Assessment
# Measures the overhead of the AIOps agent on system resources
# =============================================================

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
AGENT_URL="http://localhost:8080"
TARGET_URL="http://localhost:5000"
PROMETHEUS_URL="http://localhost:9090"
GRAFANA_URL="http://localhost:3000"
BASELINE_DURATION=120  # 2 minutes
RESULTS_DIR="results"

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
        log "Cleaning old baseline results (keeping last $keep_count files)..."

        # Remove files older than 7 days
        find "$RESULTS_DIR" -name "baseline_*.txt" -type f -mtime +7 -delete 2>/dev/null || true

        # Keep only the most recent files (by modification time)
        ls -t "$RESULTS_DIR"/baseline_*.txt 2>/dev/null | tail -n +$((keep_count + 1)) | xargs rm -f 2>/dev/null || true
    fi
}

# Command line argument parsing
if [ "$1" = "--clean" ]; then
    mkdir -p "$RESULTS_DIR"
    cleanup_old_results 0  # Remove all results
    ok "All baseline results cleaned!"
    exit 0
fi

if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --clean    Clean all baseline result files"
    echo "  --help,    Show this help message"
    echo ""
    echo "Run without options to execute baseline performance assessment."
    exit 0
fi

# Automatic cleanup of old results
cleanup_old_results 2

# Create results directory
mkdir -p "$RESULTS_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="$RESULTS_DIR/baseline_$TIMESTAMP.txt"

# =============================================================
# Step 1: Prerequisites Check
# =============================================================
section "Step 1: Prerequisites Check"

log "Checking if Docker Compose is running..."
# docker compose ps: List all containers managed by docker-compose
# This ensures the entire AIOps stack is running
cd ../..  # Go to project root where docker-compose.yml is located
if ! docker compose ps | grep -q "Up"; then
    err "Docker Compose is not running! Start with: docker compose up -d"
fi
ok "Docker Compose is running"
cd demos/demo1-baseline  # Return to demo directory

log "Checking if target application is accessible..."
# curl -s -f: Silent mode, fail on HTTP errors
# This validates the target app is responding to requests
if ! curl -s -f "$TARGET_URL/health" > /dev/null; then
    err "Target application not accessible at $TARGET_URL"
fi
ok "Target application is healthy"

log "Checking if Prometheus is accessible..."
# Validates that Prometheus is collecting metrics
if ! curl -s -f "$PROMETHEUS_URL/-/healthy" > /dev/null; then
    err "Prometheus not accessible at $PROMETHEUS_URL"
fi
ok "Prometheus is healthy"

log "Checking if AI Agent is accessible..."
# Validates the AI agent webhook receiver is ready
if ! curl -s -f "$AGENT_URL/health" > /dev/null; then
    err "AI Agent not accessible at $AGENT_URL"
fi
ok "AI Agent is healthy"

ok "All prerequisites satisfied"

# =============================================================
# Step 2: Baseline WITHOUT AI Agent
# =============================================================
section "Step 2: Baseline WITHOUT AI Agent (${BASELINE_DURATION}s)"

log "Stopping AI Agent to measure baseline overhead..."
# docker compose stop: Gracefully stops the agent container
# This allows us to measure system performance WITHOUT AI overhead
cd ../..  # Go to project root
docker compose stop agent
ok "AI Agent stopped"
cd demos/demo1-baseline  # Return to demo directory

log "Waiting 10s for system to stabilize..."
sleep 10

log "Recording baseline metrics (WITHOUT AI Agent)..."
# docker stats --no-stream: Get current resource usage snapshot
# We capture: CPU%, MEM%, NET I/O for the target container
baseline_stats=$(docker stats --no-stream --format "{{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" target-app 2>/dev/null || echo "N/A")

echo "=== BASELINE WITHOUT AI AGENT ===" | tee -a "$RESULT_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "Container Stats:" | tee -a "$RESULT_FILE"
echo "$baseline_stats" | tee -a "$RESULT_FILE"

# Query Prometheus for precise CPU usage
# This PromQL query calculates the rate of CPU usage over 1 minute
baseline_cpu=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=rate(process_cpu_seconds_total[1m])*100" 2>/dev/null | grep -o '"value":\[[^]]*\]' | head -1 || echo "N/A")

echo "Prometheus CPU Rate: $baseline_cpu" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

ok "Baseline metrics recorded"

log "Monitoring system for ${BASELINE_DURATION} seconds..."
log "💡 TIP: Open Grafana at $GRAFANA_URL to visualize metrics in real-time"
log "    - Login: admin/admin123"
log "    - Dashboard: 'NT531 AIOps System Overview'"

# Generate some light load during baseline
log "Generating light background load..."
for i in {1..10}; do
    curl -s "$TARGET_URL/" > /dev/null &
    sleep 12
done

wait
ok "Baseline period completed"

# =============================================================
# Step 3: Measurement WITH AI Agent
# =============================================================
section "Step 3: Measurement WITH AI Agent (${BASELINE_DURATION}s)"

log "Starting AI Agent..."
# docker compose start: Starts the stopped agent container
# This enables the AI-powered monitoring and remediation
cd ../..  # Go to project root
docker compose start agent
cd demos/demo1-baseline  # Return to demo directory

log "Waiting 15s for agent to initialize..."
sleep 15

log "Verifying agent health..."
if ! curl -s -f "$AGENT_URL/health" > /dev/null; then
    err "AI Agent failed to start properly"
fi
ok "AI Agent is healthy and ready"

log "Recording metrics WITH AI Agent active..."
# Same metrics collection, but now WITH the AI agent running
with_agent_stats=$(docker stats --no-stream --format "{{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" target-app agent 2>/dev/null || echo "N/A")

echo "=== WITH AI AGENT ACTIVE ===" | tee -a "$RESULT_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "Container Stats:" | tee -a "$RESULT_FILE"
echo "$with_agent_stats" | tee -a "$RESULT_FILE"

# Agent-specific metrics
agent_cpu=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=rate(process_cpu_seconds_total{job=\"agent\"}[1m])*100" 2>/dev/null | grep -o '"value":\[[^]]*\]' | head -1 || echo "N/A")

echo "Agent CPU Rate: $agent_cpu" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

log "Monitoring system with AI Agent for ${BASELINE_DURATION} seconds..."

# Send a test alert to verify agent functionality
log "Sending test alert to verify AI Agent processing..."
test_alert='{
    "alerts": [{
        "status": "firing",
        "labels": {
            "alertname": "BaselineTest",
            "severity": "info",
            "demo": "baseline"
        },
        "annotations": {
            "summary": "Baseline performance test",
            "description": "Testing agent overhead and responsiveness"
        },
        "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    }]
}'

# curl -X POST: Send POST request to agent webhook
# -H: Set Content-Type header for JSON
# -d: Send JSON alert payload
agent_response=$(curl -s -X POST "$AGENT_URL/webhook" \
    -H 'Content-Type: application/json' \
    -d "$test_alert")

echo "=== AI AGENT TEST RESPONSE ===" | tee -a "$RESULT_FILE"
echo "$agent_response" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Generate same light load WITH agent active
log "Generating light background load..."
for i in {1..10}; do
    curl -s "$TARGET_URL/" > /dev/null &
    sleep 12
done

wait
ok "AI Agent measurement period completed"

# =============================================================
# Step 4: Results Summary
# =============================================================
section "Step 4: Results Summary"

log "Collecting final metrics..."

# Get agent decision logs
recent_logs=$(curl -s "$AGENT_URL/logs?limit=3" 2>/dev/null || echo "Logs unavailable")

echo "=== AI AGENT RECENT ACTIVITY ===" | tee -a "$RESULT_FILE"
echo "$recent_logs" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

echo "=== SUMMARY ===" | tee -a "$RESULT_FILE"
echo "Test Duration: $((BASELINE_DURATION * 2))s total" | tee -a "$RESULT_FILE"
echo "Results saved to: $RESULT_FILE" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

ok "Demo 1 completed successfully!"
echo ""
log "📊 Results saved to: $RESULT_FILE"
log "📈 View detailed metrics in Grafana: $GRAFANA_URL"
log "🤖 View agent logs: curl $AGENT_URL/logs | jq"
echo ""
log "💡 Next Steps:"
log "   1. Run validation: ./validate.sh $RESULT_FILE"
log "   2. Compare metrics in Grafana dashboard"
log "   3. Review agent decision logs"
echo ""
echo -e "${GREEN}✅ Demo 1 (Baseline Assessment) Complete!${NC}"
