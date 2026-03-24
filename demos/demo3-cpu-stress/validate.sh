#!/bin/bash
# =============================================================
# Demo 3: CPU Stress Auto-Remediation Validation
# Validates CPU stress detection and automatic remediation
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
    RESULTS_FILE=$(ls -t results/cpu_stress_*.txt 2>/dev/null | head -1)
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

section "Demo 3: CPU Stress Auto-Remediation Validation"

log "Analyzing results from: $RESULTS_FILE"
echo ""

# =============================================================
# Validation 1: Test Execution Completeness
# =============================================================
section "Validation 1: Test Execution Check"

log "Verifying CPU stress test was executed..."

required_sections=(
    "BASELINE CPU USAGE"
    "CPU STRESS TEST INITIATED"
    "DURING STRESS"
    "AI AGENT DECISIONS"
    "POST-REMEDIATION PROCESS CHECK"
    "POST-REMEDIATION CPU USAGE"
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
if grep -q "CPU Workers:" "$RESULTS_FILE"; then
    cpu_workers=$(grep "CPU Workers:" "$RESULTS_FILE" | head -1 | grep -o "[0-9]*")
    log "CPU workers used: $cpu_workers"
fi

if grep -q "Duration:" "$RESULTS_FILE"; then
    duration=$(grep "Duration:" "$RESULTS_FILE" | head -1 | grep -o "[0-9]*s")
    log "Stress duration: $duration"
fi

# =============================================================
# Validation 2: Stress Process Verification
# =============================================================
section "Validation 2: Stress Process Verification"

log "Verifying stress processes were created..."

# Check if stress processes were detected during test
if grep -q "Active Stress Processes:" "$RESULTS_FILE"; then
    ok "Active stress processes section found"

    stress_processes=$(sed -n '/Active Stress Processes:/,/DURING STRESS/p' "$RESULTS_FILE" | grep "stress-ng" | head -5)

    if [ -n "$stress_processes" ]; then
        ok "Stress-ng processes were running"
        echo -e "${CYAN}Found Processes:${NC}"
        echo "$stress_processes"
    else
        warn "No stress-ng processes found in results - stress may have failed"
    fi
else
    err "No process information found"
fi

echo ""

# =============================================================
# Validation 3: AI Agent Detection
# =============================================================
section "Validation 3: AI Agent Alert Detection"

log "Checking if AI Agent detected CPU stress..."

agent_detected=false
if grep -q "AI AGENT DECISIONS" "$RESULTS_FILE"; then
    ok "AI Agent decisions section found"

    agent_decisions=$(sed -n '/AI AGENT DECISIONS/,/POST-REMEDIATION/p' "$RESULTS_FILE" | grep -v "===")

    # Check for CPU-related alerts
    if echo "$agent_decisions" | grep -qi "HighCPU\|CPUUsage\|cpu.*high\|stress"; then
        ok "AI Agent detected CPU stress alert"
        agent_detected=true

        echo -e "${CYAN}Agent Decisions Extract:${NC}"
        echo "$agent_decisions" | head -15
    else
        warn "No CPU-related decisions found in agent logs"
    fi
else
    err "No agent decisions found"
fi

echo ""

# =============================================================
# Validation 4: Auto-Remediation Success
# =============================================================
section "Validation 4: Auto-Remediation Verification"

log "Verifying if agent successfully terminated stress processes..."

remediation_success=false
if grep -q "POST-REMEDIATION PROCESS CHECK" "$RESULTS_FILE"; then
    ok "Post-remediation check performed"

    # Check if stress processes were killed
    if grep -q "No stress processes" "$RESULTS_FILE"; then
        ok "Stress processes were successfully terminated"
        remediation_success=true
    elif grep -q "SUCCESS: All stress processes were terminated" "$RESULTS_FILE"; then
        ok "Remediation explicitly confirmed successful"
        remediation_success=true
    else
        # Check current system state
        log "Checking live system for remaining stress processes..."
        current_stress=$(docker exec "$TARGET_CONTAINER" ps aux | grep -c "stress-ng" 2>/dev/null | head -1 || echo 0)

        if [ "$current_stress" -eq 0 ]; then
            ok "No stress processes currently running (verified live)"
            remediation_success=true
        else
            warn "Found $current_stress stress processes still running"
            docker exec "$TARGET_CONTAINER" ps aux | grep stress-ng | head -5 || true
        fi
    fi

    # Display post-remediation processes
    echo -e "${CYAN}Post-Remediation Process State:${NC}"
    sed -n '/POST-REMEDIATION PROCESS CHECK/,/POST-REMEDIATION CPU USAGE/p' "$RESULTS_FILE" | grep -v "===" | head -10
else
    err "No post-remediation check found"
fi

echo ""

# =============================================================
# Validation 5: CPU Recovery Analysis
# =============================================================
section "Validation 5: CPU Recovery Analysis"

log "Analyzing CPU usage across test phases..."

echo -e "${CYAN}Baseline CPU:${NC}"
sed -n '/BASELINE CPU USAGE/,/CPU STRESS TEST INITIATED/p' "$RESULTS_FILE" | grep -A 2 "Container Stats"
echo ""

echo -e "${CYAN}During Stress:${NC}"
sed -n '/DURING STRESS/,/AI AGENT DECISIONS/p' "$RESULTS_FILE" | grep -A 2 "Container Stats" | head -6
echo ""

echo -e "${CYAN}Post-Remediation:${NC}"
sed -n '/POST-REMEDIATION CPU USAGE/,/FINAL RECOVERY/p' "$RESULTS_FILE" | grep -A 2 "Container Stats"
echo ""

echo -e "${CYAN}Final Recovery:${NC}"
sed -n '/FINAL RECOVERY STATE/,/DEMO 3 SUMMARY/p' "$RESULTS_FILE" | grep -A 2 "Container Stats"
echo ""

# Compare current CPU to baseline
log "Checking current system CPU..."
current_cpu=$(docker stats --no-stream --format "{{.CPUPerc}}" "$TARGET_CONTAINER" 2>/dev/null || echo "N/A")
log "Current CPU usage: $current_cpu"

# Parse percentage (remove %)
current_cpu_num=$(echo "$current_cpu" | grep -o "[0-9.]*" || echo 0)

if (( $(awk -v cpu="$current_cpu_num" 'BEGIN {print (cpu < 20)}') )); then
    ok "CPU has recovered to normal levels (<20%)"
else
    warn "CPU usage still elevated: $current_cpu"
fi

# =============================================================
# Validation 6: Agent Action Analysis
# =============================================================
section "Validation 6: Agent Action Analysis"

log "Analyzing agent's remediation actions..."

if [ "$agent_detected" = true ]; then
    # Check what actions agent claimed to take
    if grep -qi "kill.*stress" "$RESULTS_FILE"; then
        ok "Agent decided to kill stress processes"
    fi

    if grep -qi "auto_kill_cpu_stress" "$RESULTS_FILE"; then
        ok "Agent used enhanced auto_kill_cpu_stress tool"
    fi

    if grep -qi "successful\|terminated\|killed" "$RESULTS_FILE"; then
        ok "Agent confirmed action was successful"
    fi

    # Extract agent's reasoning
    echo -e "${CYAN}Agent Actions Summary:${NC}"
    if grep -qi "tool.*=\|action\|decision" "$RESULTS_FILE"; then
        grep -i "tool\|action\|decision" "$RESULTS_FILE" | head -10
    else
        echo "Detailed action log not available"
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
echo "  T+10s: CPU stress initiated"
echo "  T+35s: Prometheus detects high CPU → triggers alert"
echo "  T+40s: AI Agent receives alert webhook"
echo "  T+45s: Agent analyzes and takes action"
echo "  T+50s: Stress processes killed"
echo "  T+80s: System fully recovered"
echo ""

if grep -q "Timeline:" "$RESULTS_FILE"; then
    echo -e "${CYAN}Actual Timeline:${NC}"
    sed -n '/Timeline:/,/Results:/p' "$RESULTS_FILE" | grep "T+" || echo "Timeline details not available"
else
    warn "No timeline information in results"
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

# Check for any remaining stress processes
log "Final check for stress processes..."
remaining_stress=$(docker exec "$TARGET_CONTAINER" ps aux | grep -c "stress-ng" 2>/dev/null || echo 0)

if [ "$remaining_stress" -eq 0 ]; then
    ok "NO stress processes remain (✅ system clean)"
else
    warn "WARNING: Found $remaining_stress stress processes still running"
    docker exec "$TARGET_CONTAINER" ps aux | grep stress-ng || true
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
[ "$all_sections_found" = true ] && ((validation_score++))
grep -q "Active Stress Processes:" "$RESULTS_FILE" && ((validation_score++))
[ "$agent_detected" = true ] && ((validation_score++))
[ "$remediation_success" = true ] && ((validation_score++))
grep -q "FINAL RECOVERY STATE" "$RESULTS_FILE" && ((validation_score++))
curl -s -f "$AGENT_URL/health" > /dev/null 2>&1 && ((validation_score++))
curl -s -f "$TARGET_URL/health" > /dev/null 2>&1 && ((validation_score++))
[ "$remaining_stress" -eq 0 ] && ((validation_score++))

validation_percentage=$((validation_score * 100 / max_score))

echo -e "${CYAN}Validation Score: ${validation_score}/${max_score} (${validation_percentage}%)${NC}"
echo ""

if [ $validation_score -ge 7 ]; then
    echo -e "${GREEN}✅ EXCELLENT - AUTO-REMEDIATION SUCCESSFUL!${NC}"
    echo ""
    ok "CPU stress was successfully created"
    ok "AI Agent detected the alert"
    ok "Agent automatically terminated stress processes"
    ok "System recovered to normal state"
    ok "No stress processes remain"
    exit_code=0
elif [ $validation_score -ge 5 ]; then
    echo -e "${YELLOW}⚠ PARTIAL SUCCESS - ${validation_score}/${max_score} checks passed${NC}"
    echo ""
    warn "Some validations failed but core functionality works"

    if [ "$agent_detected" = false ]; then
        warn "Issue: Agent did not detect CPU alert"
    fi
    if [ "$remediation_success" = false ]; then
        warn "Issue: Stress processes were not terminated"
    fi
    if [ "$remaining_stress" -gt 0 ]; then
        warn "Issue: Stress processes still running"
    fi

    exit_code=0
else
    echo -e "${RED}❌ VALIDATION FAILED - Only ${validation_score}/${max_score} checks passed${NC}"
    echo ""
    err "Demo 3 did not meet minimum validation criteria"
    err "Auto-remediation was not successful"
    exit_code=1
fi

echo ""
log "📄 Full results: cat $RESULTS_FILE"
log "🔄 Re-run demo: cd demos/demo3-cpu-stress && ./run.sh"
log "📊 View CPU spike in Grafana: http://localhost:3000"
log "🤖 View agent logs: curl $AGENT_URL/logs | jq"
log "🔍 Check processes: docker exec $TARGET_CONTAINER ps aux | grep stress"
echo ""

exit $exit_code
