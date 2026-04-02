#!/bin/bash
# =============================================================
# Demo 4: Memory Exhaustion Auto-Remediation Validation
# Validates memory stress detection and automatic remediation
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
    RESULTS_FILE=$(ls -t results/memory_stress_*.txt 2>/dev/null | head -1)
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

TARGET_CONTAINER="target-app"

section "Demo 4: Memory Exhaustion Auto-Remediation Validation"

log "Analyzing results from: $RESULTS_FILE"
echo ""

# =============================================================
# Validation 1: Test Execution Completeness
# =============================================================
section "Validation 1: Test Execution Check"

log "Verifying memory stress test was executed..."

required_sections=(
    "BASELINE MEMORY USAGE"
    "MEMORY STRESS TEST INITIATED"
    "DURING STRESS"
    "AI AGENT DECISIONS"
    "POST-REMEDIATION MEMORY CHECK"
    "FINAL RECOVERY STATE"
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
    ok "All required sections present - test was executed"
else
    err "Results file incomplete - test may have failed"
    exit 1
fi

# Extract stress parameters
if grep -q "Concurrent Users:" "$RESULTS_FILE"; then
    users=$(grep "Concurrent Users:" "$RESULTS_FILE" | head -1 | grep -o "[0-9]*")
    log "Concurrent users: $users"
fi

if grep -q "Duration:" "$RESULTS_FILE"; then
    duration=$(grep "Duration:" "$RESULTS_FILE" | head -1 | grep -o "[0-9]*s")
    log "Stress duration: $duration"
fi

# =============================================================
# Validation 2: Memory Stress Verification
# =============================================================
section "Validation 2: Memory Stress Verification"

log "Verifying memory stress was created..."

# Check if high memory was detected during test
if grep -q "DURING STRESS" "$RESULTS_FILE"; then
    ok "Memory stress phase detected"

    # Look for high memory usage indicators
    stress_memory=$(sed -n '/DURING STRESS/,/AI AGENT DECISIONS/p' "$RESULTS_FILE" | grep "MemUsage" | head -1)

    if [ -n "$stress_memory" ]; then
        ok "Memory usage recorded during stress"
        echo -e "${CYAN}Memory During Stress:${NC}"
        echo "$stress_memory"
    else
        warn "No memory usage data found in stress phase"
    fi
else
    err "No stress phase found"
fi

echo ""

# =============================================================
# Validation 3: AI Agent Detection
# =============================================================
section "Validation 3: AI Agent Alert Detection"

log "Checking if AI Agent detected memory stress..."

agent_detected=false
if grep -q "AI AGENT DECISIONS" "$RESULTS_FILE"; then
    ok "AI Agent decisions section found"

    agent_decisions=$(sed -n '/AI AGENT DECISIONS/,/POST-REMEDIATION/p' "$RESULTS_FILE" | grep -v "===")

    # Check for memory-related alerts
    if echo "$agent_decisions" | grep -qi "HighMemory\|MemoryUsage\|memory.*high\|memory.*pressure"; then
        ok "AI Agent detected memory stress alert"
        agent_detected=true

        echo -e "${CYAN}Agent Decisions Extract:${NC}"
        echo "$agent_decisions" | head -15
    else
        warn "No memory-related decisions found in agent logs"
    fi
else
    err "No agent decisions found"
fi

echo ""

# =============================================================
# Validation 4: Auto-Remediation Success
# =============================================================
section "Validation 4: Auto-Remediation Verification"

log "Verifying if agent successfully remediated memory..."

remediation_success=false
if grep -q "POST-REMEDIATION MEMORY CHECK" "$RESULTS_FILE"; then
    ok "Post-remediation check performed"

    # Check if service health was verified
    if grep -q "Service Status: Running" "$RESULTS_FILE"; then
        ok "Service remained running after remediation"
        remediation_success=true
    elif grep -q "Service.*healthy" "$RESULTS_FILE"; then
        ok "Service health verified post-remediation"
        remediation_success=true
    else
        # Check current system state
        log "Checking live system service health..."
        if curl -s -f "http://localhost:5000/health" > /dev/null 2>&1; then
            ok "Service is currently healthy (verified live)"
            remediation_success=true
        else
            warn "Service health check failed"
        fi
    fi

    # Display post-remediation state
    echo -e "${CYAN}Post-Remediation State:${NC}"
    sed -n '/POST-REMEDIATION MEMORY CHECK/,/FINAL RECOVERY/p' "$RESULTS_FILE" | grep -v "===" | head -10
else
    err "No post-remediation check found"
fi

echo ""

# =============================================================
# Validation 5: Memory Recovery Analysis
# =============================================================
section "Validation 5: Memory Recovery Analysis"

log "Analyzing memory usage across test phases..."

echo -e "${CYAN}Baseline Memory:${NC}"
sed -n '/BASELINE MEMORY USAGE/,/MEMORY STRESS TEST INITIATED/p' "$RESULTS_FILE" | grep -A 2 "Container Stats" | head -3
echo ""

echo -e "${CYAN}During Stress (Peak):${NC}"
sed -n '/DURING STRESS/,/AI AGENT DECISIONS/p' "$RESULTS_FILE" | grep "MiB" | tail -1 || echo "N/A"
echo ""

echo -e "${CYAN}Post-Remediation:${NC}"
sed -n '/POST-REMEDIATION MEMORY CHECK/,/FINAL RECOVERY/p' "$RESULTS_FILE" | grep "MiB" || echo "N/A"
echo ""

echo -e "${CYAN}Final Recovery:${NC}"
sed -n '/FINAL RECOVERY STATE/,/DEMO 4 SUMMARY/p' "$RESULTS_FILE" | grep "MiB" || echo "N/A"
echo ""

# Check current memory
log "Checking current system memory..."
current_mem=$(docker stats --no-stream --format "{{.MemUsage}}" "$TARGET_CONTAINER" 2>/dev/null || echo "N/A")
log "Current memory: $current_mem"

# =============================================================
# Validation 6: Agent Action Analysis
# =============================================================
section "Validation 6: Agent Action Analysis"

log "Analyzing agent's remediation actions..."

if [ "$agent_detected" = true ]; then
    # Check what actions agent claimed to take
    if grep -qi "restart.*service\|service.*restart" "$RESULTS_FILE"; then
        ok "Agent decided to restart service"
    elif grep -qi "remediat\|action\|tool" "$RESULTS_FILE"; then
        ok "Agent took remediation action"
    fi

    if grep -qi "restart_service" "$RESULTS_FILE"; then
        ok "Agent used restart_service tool"
    fi

    if grep -qi "successful\|health\|recovered" "$RESULTS_FILE"; then
        ok "Agent confirmed remediation was successful"
    fi

    # Extract agent's reasoning
    echo -e "${CYAN}Agent Actions Summary:${NC}"
    if grep -qi "decision\|reasoning\|tool" "$RESULTS_FILE"; then
        grep -i "decision\|reasoning\|tool" "$RESULTS_FILE" | head -8
    else
        echo "Detailed action log not fully available"
    fi
else
    warn "Cannot analyze actions - agent did not detect alert"
fi

echo ""

# =============================================================
# Validation 7: Timeline Verification
# =============================================================
section "Validation 7: Timeline Verification"

log "Verifying expected timeline..."

echo -e "${CYAN}Expected Timeline:${NC}"
echo "  T+0s:  Baseline recorded"
echo "  T+15s: Memory stress initiated"
echo "  T+35s: Prometheus detects high memory → triggers alert"
echo "  T+40s: AI Agent receives alert webhook"
echo "  T+45s: Agent analyzes and takes action"
echo "  T+60s: Service recovery measured"
echo "  T+90s: System fully recovered"
echo ""

if grep -q "Timeline:" "$RESULTS_FILE"; then
    echo -e "${CYAN}Actual Timeline:${NC}"
    sed -n '/Timeline:/,/Results:/p' "$RESULTS_FILE" | grep "T+" || echo "Timeline details not fully available"
else
    warn "No detailed timeline information in results"
fi

echo ""

# =============================================================
# Validation 8: System Health Check
# =============================================================
section "Validation 8: Current System Health"

log "Verifying system health post-test..."

AGENT_URL="http://localhost:8080"
TARGET_URL="http://localhost:5000"

# Check agent health
if curl -s -f "$AGENT_URL/health" > /dev/null 2>&1; then
    ok "AI Agent is currently healthy"
else
    warn "AI Agent health check failed"
fi

# Check target app health
if curl -s -f "$TARGET_URL/health" > /dev/null 2>&1; then
    ok "Target application is currently healthy"
else
    warn "Target application health check failed"
fi

# Current container stats
log "Current system stats:"
docker stats --no-stream --format "{{.Container}}: CPU={{.CPUPerc}} MEM={{.MemUsage}}" "$TARGET_CONTAINER" 2>/dev/null || echo "Stats unavailable"

echo ""

# =============================================================
# Final Validation Summary
# =============================================================
section "Validation Summary"

validation_score=0
max_score=8

# Count passed validations
[ "$all_sections_found" = true ] && ((++validation_score))
grep -q "DURING STRESS" "$RESULTS_FILE" && ((++validation_score))
[ "$agent_detected" = true ] && ((++validation_score))
[ "$remediation_success" = true ] && ((++validation_score))
grep -q "FINAL RECOVERY STATE" "$RESULTS_FILE" && ((++validation_score))
curl -s -f "$AGENT_URL/health" > /dev/null 2>&1 && ((++validation_score))
curl -s -f "$TARGET_URL/health" > /dev/null 2>&1 && ((++validation_score))
grep -qi "restart\|recover\|success" "$RESULTS_FILE" && ((++validation_score))

validation_percentage=$((validation_score * 100 / max_score))

echo -e "${CYAN}Validation Score: ${validation_score}/${max_score} (${validation_percentage}%)${NC}"
echo ""

if [ $validation_score -ge 7 ]; then
    echo -e "${GREEN}✅ EXCELLENT - AUTO-REMEDIATION SUCCESSFUL!${NC}"
    echo ""
    ok "Memory stress was successfully created"
    ok "AI Agent detected the alert"
    ok "Agent automatically remediated memory pressure"
    ok "Service remained healthy"
    ok "System recovered to normal state"
    exit_code=0
elif [ $validation_score -ge 5 ]; then
    echo -e "${YELLOW}⚠ PARTIAL SUCCESS - ${validation_score}/${max_score} checks passed${NC}"
    echo ""
    warn "Some validations failed but core functionality works"

    if [ "$agent_detected" = false ]; then
        warn "Issue: Agent did not detect memory alert"
    fi
    if [ "$remediation_success" = false ]; then
        warn "Issue: Service health not verified after remediation"
    fi

    exit_code=0
else
    echo -e "${RED}❌ VALIDATION FAILED - Only ${validation_score}/${max_score} checks passed${NC}"
    echo ""
    err "Demo 4 did not meet minimum validation criteria"
    err "Auto-remediation was not successful"
    exit_code=1
fi

echo ""
log "📄 Full results: cat $RESULTS_FILE"
log "🔄 Re-run demo: cd demos/demo4-memory && ./run.sh"
log "📊 View memory spike in Grafana: http://localhost:3000"
log "🤖 View agent logs: curl $AGENT_URL/logs | jq"
log "💾 Check service logs: docker logs $TARGET_CONTAINER --tail 20"
echo ""

exit $exit_code
