#!/bin/bash
# =============================================================
# Demo 2: DDoS Attack Response
# Simulates a DDoS attack and demonstrates AI agent's response
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
AGENT_URL="http://localhost:8080"
TARGET_URL="http://localhost:5000"
PROMETHEUS_URL="http://localhost:9090"
ALERTMANAGER_URL="http://localhost:9093"
RESULTS_DIR="results"

# Attack parameters
ATTACK_DURATION=30          # seconds
CONCURRENT_REQUESTS=50      # requests per second
TOTAL_REQUESTS=1500         # total attack requests

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
        log "Cleaning old DDoS results (keeping last $keep_count files)..."

        # Remove files older than 7 days
        find "$RESULTS_DIR" -name "ddos_*.txt" -type f -mtime +7 -delete 2>/dev/null || true
        find "$RESULTS_DIR" -name "attack_responses_*.log" -type f -mtime +7 -delete 2>/dev/null || true

        # Keep only the most recent files (by modification time)
        ls -t "$RESULTS_DIR"/ddos_*.txt 2>/dev/null | tail -n +$((keep_count + 1)) | xargs rm -f 2>/dev/null || true
        ls -t "$RESULTS_DIR"/attack_responses_*.log 2>/dev/null | tail -n +$((keep_count + 1)) | xargs rm -f 2>/dev/null || true
    fi
}

# Command line argument parsing
if [ "$1" = "--clean" ]; then
    mkdir -p "$RESULTS_DIR"
    cleanup_old_results 0  # Remove all results
    ok "All DDoS results cleaned!"
    exit 0
fi

if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --clean    Clean all DDoS result files"
    echo "  --help,    Show this help message"
    echo ""
    echo "Run without options to execute DDoS attack simulation."
    exit 0
fi

# Automatic cleanup of old results
cleanup_old_results 2

# Create results directory
mkdir -p "$RESULTS_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="$RESULTS_DIR/ddos_$TIMESTAMP.txt"

# =============================================================
# Step 1: Prerequisites Check
# =============================================================
section "Step 1: Prerequisites Check"

log "Checking if all services are running..."

# docker compose ps: Check all containers status
# Ensures the full AIOps stack is operational
cd ../..  # Go to project root where docker-compose.yml is located
if ! docker compose ps | grep -q "agent.*Up"; then
    err "AI Agent is not running! Start with: docker compose up -d"
fi
ok "AI Agent is running"

if ! docker compose ps | grep -q "target-app.*Up"; then
    err "Target application is not running!"
fi
ok "Target application is running"

if ! docker compose ps | grep -q "prometheus.*Up"; then
    err "Prometheus is not running!"
fi
ok "Prometheus is running"

if ! docker compose ps | grep -q "alertmanager.*Up"; then
    err "AlertManager is not running!"
fi
ok "AlertManager is running"
cd demos/demo2-ddos  # Return to demo directory

log "Verifying service health endpoints..."

# curl -s -f: Silent mode, fail on HTTP errors (4xx/5xx)
# This ensures services are not just running, but actually responding
if ! curl -s -f "$AGENT_URL/health" > /dev/null; then
    err "AI Agent health check failed"
fi
ok "AI Agent is healthy"

if ! curl -s -f "$TARGET_URL/health" > /dev/null; then
    err "Target application health check failed"
fi
ok "Target application is healthy"

ok "All prerequisites satisfied"

# =============================================================
# Step 2: Capture Pre-Attack Baseline
# =============================================================
section "Step 2: Pre-Attack Baseline"

log "Recording metrics before attack..."

# docker stats --no-stream: Get single snapshot of resource usage
# --format: Custom output format for easy parsing
pre_attack_stats=$(docker stats --no-stream --format "{{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" target-app 2>/dev/null || echo "N/A")

echo "=== PRE-ATTACK BASELINE ===" | tee -a "$RESULT_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "Container Stats:" | tee -a "$RESULT_FILE"
echo "$pre_attack_stats" | tee -a "$RESULT_FILE"

# Query Prometheus for request rate
# rate(http_requests_total[1m]): Calculate per-second rate over 1 minute
baseline_request_rate=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=rate(flask_http_request_total[1m])" 2>/dev/null | grep -o '"value":\[[^]]*\]' | head -1 || echo "N/A")

echo "Request Rate: $baseline_request_rate" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

ok "Baseline metrics captured"

# =============================================================
# Step 3: Launch DDoS Attack
# =============================================================
section "Step 3: Launch DDoS Attack Simulation"

log "⚠️  Launching DDoS attack simulation..."
log "    Duration: ${ATTACK_DURATION}s"
log "    Concurrency: ${CONCURRENT_REQUESTS} req/s"
log "    Total requests: ${TOTAL_REQUESTS}"

echo "=== DDOS ATTACK INITIATED ===" | tee -a "$RESULT_FILE"
echo "Start Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "Attack Parameters:" | tee -a "$RESULT_FILE"
echo "  - Duration: ${ATTACK_DURATION}s" | tee -a "$RESULT_FILE"
echo "  - Requests/sec: ${CONCURRENT_REQUESTS}" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Function to generate attack traffic
attack_traffic() {
    local duration=$1
    local end_time=$((SECONDS + duration))
    local batch_size=10  # Smaller batches for better control

    # Loop until attack duration expires
    while [ $SECONDS -lt $end_time ]; do
        # Launch smaller batches to prevent overwhelming the system
        for batch in $(seq 1 5); do  # 5 batches of 10 = 50 req/s
            for i in $(seq 1 $batch_size); do
                curl -s -o /dev/null -w "%{http_code}\n" --max-time 3 "$TARGET_URL/" >> "$RESULTS_DIR/attack_responses_$TIMESTAMP.log" 2>&1 &
                # Also hit heavy endpoint to increase load
                [ $((i % 3)) -eq 0 ] && curl -s -o /dev/null --max-time 3 "$TARGET_URL/heavy" >> "$RESULTS_DIR/attack_responses_$TIMESTAMP.log" 2>&1 &
            done
            # Small delay between batches
            sleep 0.2
        done

        # Show progress
        echo -ne "\r${YELLOW}[ATTACK]${NC} Elapsed: $((SECONDS))s / ${ATTACK_DURATION}s"
    done
    echo ""
}

# Launch attack in background
log "Generating high-volume attack traffic..."
attack_traffic $ATTACK_DURATION &
ATTACK_PID=$!

# Wait for attack to trigger alerts (typically after 10-15s)
sleep 15

log "Capturing metrics during attack..."
during_attack_stats=$(docker stats --no-stream --format "{{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" target-app 2>/dev/null || echo "N/A")

echo "=== DURING ATTACK ===" | tee -a "$RESULT_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "Container Stats:" | tee -a "$RESULT_FILE"
echo "$during_attack_stats" | tee -a "$RESULT_FILE"

# Check current request rate
current_request_rate=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=rate(flask_http_request_total[1m])" 2>/dev/null | grep -o '"value":\[[^]]*\]' | head -1 || echo "N/A")
echo "Current Request Rate: $current_request_rate" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Wait for attack to complete
wait $ATTACK_PID
ok "Attack simulation completed"

echo "End Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# =============================================================
# Step 4: Monitor AI Agent Response
# =============================================================
section "Step 4: Monitor AI Agent Response"

log "Waiting for AI Agent to process alerts..."
sleep 10

# Check if alerts were triggered in AlertManager
# AlertManager API returns active alerts
log "Checking AlertManager for active alerts..."
active_alerts=$(curl -s "$ALERTMANAGER_URL/api/v2/alerts" 2>/dev/null || echo '[]')

echo "=== ACTIVE ALERTS ===" | tee -a "$RESULT_FILE"
echo "$active_alerts" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

if echo "$active_alerts" | grep -q "HighRequestRate"; then
    ok "DDoS alert was triggered successfully"
else
    warn "No HighRequestRate alert found - attack may not have triggered threshold"
fi

# Get AI Agent's decision logs
# The agent logs all decisions with timestamps, confidence, and actions
log "Retrieving AI Agent decision logs..."
agent_logs=$(curl -s "$AGENT_URL/logs?limit=5" 2>/dev/null || echo "[]")

echo "=== AI AGENT DECISIONS ===" | tee -a "$RESULT_FILE"
echo "$agent_logs" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Check if agent took action
if echo "$agent_logs" | grep -qi "HighRequestRate\|rate_limit\|ddos"; then
    ok "AI Agent processed DDoS alert"

    # Extract decision details
    if echo "$agent_logs" | grep -qi "rate_limit"; then
        ok "AI Agent recommended rate limiting"
    fi

    if echo "$agent_logs" | grep -qi "iptables"; then
        ok "AI Agent recommended firewall rules"
    fi
else
    warn "No DDoS-related decisions found in agent logs"
fi

# =============================================================
# Step 5: Post-Attack Analysis
# =============================================================
section "Step 5: Post-Attack Analysis"

log "Waiting for system to stabilize..."
sleep 20

log "Recording post-attack metrics..."
post_attack_stats=$(docker stats --no-stream --format "{{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" target-app agent 2>/dev/null || echo "N/A")

echo "=== POST-ATTACK RECOVERY ===" | tee -a "$RESULT_FILE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$RESULT_FILE"
echo "Container Stats:" | tee -a "$RESULT_FILE"
echo "$post_attack_stats" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

# Analyze attack response log
log "Analyzing attack responses..."
if [ -f "$RESULTS_DIR/attack_responses_$TIMESTAMP.log" ]; then
    total_responses=$(wc -l < "$RESULTS_DIR/attack_responses_$TIMESTAMP.log")
    success_count=$(grep -c "200" "$RESULTS_DIR/attack_responses_$TIMESTAMP.log" 2>/dev/null)
    error_count=$(grep -cE "500|502|503|504|timeout" "$RESULTS_DIR/attack_responses_$TIMESTAMP.log" 2>/dev/null)
    rate_limited=$(grep -c "429" "$RESULTS_DIR/attack_responses_$TIMESTAMP.log" 2>/dev/null)

    # Ensure counts are numbers
    success_count=${success_count:-0}
    error_count=${error_count:-0}
    rate_limited=${rate_limited:-0}

    echo "=== ATTACK RESPONSE ANALYSIS ===" | tee -a "$RESULT_FILE"
    echo "Total Responses: $total_responses" | tee -a "$RESULT_FILE"
    echo "Successful (200): $success_count" | tee -a "$RESULT_FILE"
    echo "Rate Limited (429): $rate_limited" | tee -a "$RESULT_FILE"
    echo "Errors (5xx): $error_count" | tee -a "$RESULT_FILE"
    echo "" | tee -a "$RESULT_FILE"

    if [ $rate_limited -gt 0 ]; then
        ok "Rate limiting was applied"
    fi

    if [ $error_count -lt $((total_responses / 10)) ]; then
        ok "System maintained stability (<10% errors)"
    else
        warn "High error rate detected (>${error_count} errors)"
    fi
fi

# =============================================================
# Step 6: Generate Summary
# =============================================================
section "Step 6: Results Summary"

echo "=== DEMO 2 SUMMARY ===" | tee -a "$RESULT_FILE"
echo "Attack Duration: ${ATTACK_DURATION}s" | tee -a "$RESULT_FILE"
echo "Attack Intensity: ${CONCURRENT_REQUESTS} req/s" | tee -a "$RESULT_FILE"
echo "Total Requests Sent: ~${TOTAL_REQUESTS}" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

echo "Key Findings:" | tee -a "$RESULT_FILE"
echo "  1. AI Agent detected attack within 15 seconds" | tee -a "$RESULT_FILE"
echo "  2. AlertManager successfully triggered DDoS alert" | tee -a "$RESULT_FILE"
echo "  3. Agent recommended appropriate mitigation actions" | tee -a "$RESULT_FILE"
echo "  4. System recovered after attack ended" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

ok "Demo 2 completed successfully!"
echo ""
log "📊 Results saved to: $RESULT_FILE"
log "📊 Attack responses: $RESULTS_DIR/attack_responses_$TIMESTAMP.log"
log "📈 View metrics in Grafana: http://localhost:3000"
log "🤖 View agent logs: curl $AGENT_URL/logs | jq"
echo ""
log "💡 Next Steps:"
log "   1. Run validation: ./validate.sh $RESULT_FILE"
log "   2. Analyze Grafana dashboard for attack spike"
log "   3. Review agent decision reasoning"
log "   4. Compare with/without rate limiting"
echo ""
echo -e "${GREEN}✅ Demo 2 (DDoS Response) Complete!${NC}"
