#!/bin/bash
# =============================================================
# Demo 2: DDoS Response Validation
# Validates DDoS attack detection and AI agent response
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

# Utility functions
log() { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
ok()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn(){ echo -e "${YELLOW}[⚠]${NC} $1"; }
err() { echo -e "${RED}[✗]${NC} $1"; }
section() { echo -e "\n${PURPLE}═══ $1 ═══${NC}\n"; }

# Check if results file is provided
if [ -z "$1" ]; then
    RESULTS_FILE=$(ls -t results/ddos_*.txt 2>/dev/null | head -1)
    if [ -z "$RESULTS_FILE" ]; then
        err "No results file found. Run ./run.sh first or provide file path."
        echo "Usage: $0 [results_file]"
        exit 1
    fi
    log "Using most recent results: $RESULTS_FILE"
else
    RESULTS_FILE="$1"
    if [ ! -f "$RESULTS_FILE" ]; then
        err "Results file not found: $RESULTS_FILE"
        exit 1
    fi
fi

section "Demo 2: DDoS Response Validation"

log "Analyzing results from: $RESULTS_FILE"
echo ""

# =============================================================
# Validation 1: Attack Execution
# =============================================================
section "Validation 1: Attack Execution Check"

log "Verifying DDoS attack was executed..."

required_sections=(
    "PRE-ATTACK BASELINE"
    "DDOS ATTACK INITIATED"
    "DURING ATTACK"
    "ACTIVE ALERTS"
    "AI AGENT DECISIONS"
    "POST-ATTACK RECOVERY"
)

all_sections_found=true
for section_name in "${required_sections[@]}"; do
    if grep -q "$section_name" "$RESULTS_FILE"; then
        ok "Found section: $section_name"
    else
        err "Missing section: $section_name"
        all_sections_found=false
    fi
done

if [ "$all_sections_found" = true ]; then
    ok "All required sections present - attack was executed"
else
    err "Results file incomplete - attack may have failed"
    exit 1
fi

# Check attack parameters
if grep -q "Duration:" "$RESULTS_FILE"; then
    attack_duration=$(grep "Duration:" "$RESULTS_FILE" | head -1 | grep -o "[0-9]*s")
    log "Attack duration: $attack_duration"
fi

if grep -q "Requests/sec:" "$RESULTS_FILE"; then
    attack_rate=$(grep "Requests/sec:" "$RESULTS_FILE" | head -1 | grep -o "[0-9]*")
    log "Attack rate: ${attack_rate} req/s"
fi

# =============================================================
# Validation 2: Alert Triggering
# =============================================================
section "Validation 2: Alert Triggering Validation"

log "Checking if DDoS alerts were triggered..."

if grep -q "ACTIVE ALERTS" "$RESULTS_FILE"; then
    ok "Active alerts section found"

    # Check for specific DDoS-related alerts
    if grep -qi "HighRequestRate" "$RESULTS_FILE"; then
        ok "HighRequestRate alert was triggered"
        alert_triggered=true
    else
        warn "HighRequestRate alert not found"
        alert_triggered=false
    fi

    # Display alerts
    echo -e "${CYAN}Triggered Alerts:${NC}"
    sed -n '/ACTIVE ALERTS/,/AI AGENT DECISIONS/p' "$RESULTS_FILE" | grep -v "===" | head -10
else
    err "No active alerts section found"
    alert_triggered=false
fi

echo ""

# =============================================================
# Validation 3: AI Agent Response
# =============================================================
section "Validation 3: AI Agent Response Validation"

log "Analyzing AI Agent decisions..."

if grep -q "AI AGENT DECISIONS" "$RESULTS_FILE"; then
    ok "AI Agent decisions recorded"

    agent_decisions=$(sed -n '/AI AGENT DECISIONS/,/POST-ATTACK/p' "$RESULTS_FILE" | grep -v "===")

    # Check for DDoS-related decisions
    agent_responded=false
    if echo "$agent_decisions" | grep -qi "HighRequestRate\|rate_limit\|ddos\|429"; then
        ok "AI Agent responded to DDoS alert"
        agent_responded=true

        # Check for specific actions
        if echo "$agent_decisions" | grep -qi "rate_limit"; then
            ok "Agent recommended rate limiting"
        fi

        if echo "$agent_decisions" | grep -qi "iptables\|firewall"; then
            ok "Agent recommended firewall rules"
        fi

        if echo "$agent_decisions" | grep -qi "block\|drop"; then
            ok "Agent recommended blocking traffic"
        fi
    else
        warn "No DDoS-specific agent decisions found"
    fi

    # Display agent decisions
    echo -e "${CYAN}Agent Decisions:${NC}"
    echo "$agent_decisions" | head -20
else
    err "No agent decisions found"
    agent_responded=false
fi

echo ""

# =============================================================
# Validation 4: Attack Impact Analysis
# =============================================================
section "Validation 4: Attack Impact Analysis"

log "Comparing pre-attack vs during-attack metrics..."

# Extract metrics
pre_attack=$(sed -n '/PRE-ATTACK BASELINE/,/DDOS ATTACK INITIATED/p' "$RESULTS_FILE")
during_attack=$(sed -n '/DURING ATTACK/,/AI AGENT DECISIONS/p' "$RESULTS_FILE")
post_attack=$(sed -n '/POST-ATTACK RECOVERY/,/ATTACK RESPONSE ANALYSIS/p' "$RESULTS_FILE")

echo -e "${CYAN}Pre-Attack Metrics:${NC}"
echo "$pre_attack" | grep -A 3 "Container Stats"
echo ""

echo -e "${CYAN}During Attack Metrics:${NC}"
echo "$during_attack" | grep -A 3 "Container Stats"
echo ""

echo -e "${CYAN}Post-Attack Metrics:${NC}"
echo "$post_attack" | grep -A 3 "Container Stats"
echo ""

# Check if attack response analysis exists
if grep -q "ATTACK RESPONSE ANALYSIS" "$RESULTS_FILE"; then
    ok "Attack response analysis available"

    echo -e "${CYAN}Response Analysis:${NC}"
    sed -n '/ATTACK RESPONSE ANALYSIS/,/DEMO 2 SUMMARY/p' "$RESULTS_FILE" | grep -v "===" | head -10

    # Extract response counts
    total_responses=$(grep "Total Responses:" "$RESULTS_FILE" | grep -o "[0-9]*" | head -1 || echo 0)
    success_count=$(grep "Successful (200):" "$RESULTS_FILE" | grep -o "[0-9]*" | head -1 || echo 0)
    rate_limited=$(grep "Rate Limited (429):" "$RESULTS_FILE" | grep -o "[0-9]*" | head -1 || echo 0)
    error_count=$(grep "Errors (5xx):" "$RESULTS_FILE" | grep -o "[0-9]*" | head -1 || echo 0)

    log "Total responses: $total_responses"
    log "Successful: $success_count"
    log "Rate limited: $rate_limited"
    log "Errors: $error_count"

    # Calculate error rate
    if [ $total_responses -gt 0 ]; then
        error_rate=$((error_count * 100 / total_responses))
        log "Error rate: ${error_rate}%"

        if [ $error_rate -lt 10 ]; then
            ok "Low error rate (<10%) - system maintained stability"
        elif [ $error_rate -lt 30 ]; then
            warn "Moderate error rate (${error_rate}%) - system under stress"
        else
            err "High error rate (${error_rate}%) - system overloaded"
        fi
    fi

    if [ $rate_limited -gt 0 ]; then
        ok "Rate limiting was applied (${rate_limited} requests limited)"
    fi
else
    warn "No detailed response analysis available"
fi

echo ""

# =============================================================
# Validation 5: System Recovery
# =============================================================
section "Validation 5: System Recovery Check"

log "Verifying system recovered after attack..."

if grep -q "POST-ATTACK RECOVERY" "$RESULTS_FILE"; then
    ok "Post-attack metrics recorded"

    # Check if system is currently healthy
    AGENT_URL="http://localhost:8080"
    TARGET_URL="http://localhost:5000"

    if curl -s -f "$AGENT_URL/health" > /dev/null 2>&1; then
        ok "AI Agent is currently healthy"
    else
        warn "AI Agent health check failed"
    fi

    if curl -s -f "$TARGET_URL/health" > /dev/null 2>&1; then
        ok "Target application is currently healthy"
    else
        warn "Target application health check failed"
    fi

    # Check current container stats
    log "Current system stats:"
    docker stats --no-stream --format "{{.Container}}: CPU={{.CPUPerc}} MEM={{.MemUsage}}" target-app agent 2>/dev/null || echo "Stats unavailable"
else
    warn "No post-attack recovery data found"
fi

echo ""

# =============================================================
# Validation 6: Response Time Analysis
# =============================================================
section "Validation 6: Response Time Analysis"

log "Analyzing agent response timing..."

# Extract timestamps
if grep -q "Start Time:" "$RESULTS_FILE"; then
    attack_start=$(grep "Start Time:" "$RESULTS_FILE" | head -1 | cut -d: -f2-)
    log "Attack started: $attack_start"
fi

if grep -q "End Time:" "$RESULTS_FILE"; then
    attack_end=$(grep "End Time:" "$RESULTS_FILE" | head -1 | cut -d: -f2-)
    log "Attack ended: $attack_end"
fi

echo -e "${CYAN}Expected Response Timeline:${NC}"
echo "  T+0s:  Attack initiated"
echo "  T+15s: Alert should trigger (threshold reached)"
echo "  T+20s: AI Agent should process alert"
echo "  T+30s: Attack ends"
echo "  T+50s: System stabilizes"
echo ""

if [ "$alert_triggered" = true ] && [ "$agent_responded" = true ]; then
    ok "Agent detected and responded to attack"
else
    if [ "$alert_triggered" = false ]; then
        warn "Alert was not triggered - attack may not have reached threshold"
    fi
    if [ "$agent_responded" = false ]; then
        warn "Agent did not respond to attack"
    fi
fi

# =============================================================
# Final Validation Summary
# =============================================================
section "Validation Summary"

validation_score=0
max_score=7

# Count passed validations
[ "$all_sections_found" = true ] && ((validation_score++))
[ "$alert_triggered" = true ] && ((validation_score++))
[ "$agent_responded" = true ] && ((validation_score++))
grep -q "ATTACK RESPONSE ANALYSIS" "$RESULTS_FILE" && ((validation_score++))
grep -q "POST-ATTACK RECOVERY" "$RESULTS_FILE" && ((validation_score++))
curl -s -f "$AGENT_URL/health" > /dev/null 2>&1 && ((validation_score++))
curl -s -f "$TARGET_URL/health" > /dev/null 2>&1 && ((validation_score++))

validation_percentage=$((validation_score * 100 / max_score))

echo -e "${CYAN}Validation Score: ${validation_score}/${max_score} (${validation_percentage}%)${NC}"
echo ""

if [ $validation_score -ge 6 ]; then
    echo -e "${GREEN}✅ VALIDATION PASSED!${NC}"
    echo ""
    ok "DDoS attack was successfully simulated"
    ok "AI Agent detected and responded to attack"
    ok "System recovered after attack"
    ok "All critical validations passed"
    exit_code=0
elif [ $validation_score -ge 4 ]; then
    echo -e "${YELLOW}⚠ PARTIAL VALIDATION - ${validation_score}/${max_score} checks passed${NC}"
    echo ""
    warn "Some validations failed but demo partially successful"
    exit_code=0
else
    echo -e "${RED}❌ VALIDATION FAILED - Only ${validation_score}/${max_score} checks passed${NC}"
    echo ""
    err "Demo 2 did not meet minimum validation criteria"
    exit_code=1
fi

echo ""
log "📄 Full results: cat $RESULTS_FILE"
log "🔄 Re-run demo: cd demos/demo2-ddos && ./run.sh"
log "📊 View Grafana: http://localhost:3000"
log "🤖 View agent logs: curl http://localhost:8080/logs | jq"
echo ""

exit $exit_code
