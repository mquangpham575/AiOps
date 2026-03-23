#!/bin/bash
# =============================================================
# validate.sh — Comprehensive validation script for AIOps system
# Tests all 3 scenarios and validates system functionality
# =============================================================

set -e  # Exit on error

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
ok()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn(){ echo -e "${YELLOW}[⚠]${NC} $1"; }
err() { echo -e "${RED}[✗]${NC} $1"; }
test_header() { echo -e "\n${PURPLE}=== $1 ===${NC}"; }

# Configuration
PROMETHEUS_URL="http://localhost:9090"
ALERT_URL="http://localhost:9093"
GRAFANA_URL="http://localhost:3000"
AGENT_URL="http://localhost:8080"
TARGET_URL="http://localhost:5000"

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

run_test() {
    local test_name="$1"
    local test_command="$2"

    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    log "Running: $test_name"

    if eval "$test_command" > /dev/null 2>&1; then
        ok "$test_name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        err "$test_name"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# ── Test 1: System Health ─────────────────────────────────
test_system_health() {
    test_header "SYSTEM HEALTH VALIDATION"

    run_test "Docker Compose services running" \
        "docker compose ps --format json | jq -e '.[] | select(.State != \"running\") | empty'"

    run_test "Prometheus API accessible" \
        "curl -s $PROMETHEUS_URL/api/v1/status/config | jq -e '.status == \"success\"'"

    run_test "AlertManager API accessible" \
        "curl -s $ALERT_URL/api/v1/status | jq -e '.status == \"success\"'"

    run_test "Grafana accessible" \
        "curl -s -o /dev/null -w '%{http_code}' $GRAFANA_URL/api/health | grep -q '200'"

    run_test "AI Agent health check" \
        "curl -s $AGENT_URL/health | jq -e '.status == \"ok\"'"

    run_test "Target app accessible" \
        "curl -s $TARGET_URL/health | jq -e '.status == \"healthy\"'"
}

# ── Test 2: Metrics Collection ────────────────────────────
test_metrics_collection() {
    test_header "METRICS COLLECTION VALIDATION"

    run_test "Node metrics available" \
        "curl -s '$PROMETHEUS_URL/api/v1/query?query=up{job=\"node-exporter\"}' | jq -e '.data.result[0].value[1] == \"1\"'"

    run_test "Container metrics available" \
        "curl -s '$PROMETHEUS_URL/api/v1/query?query=up{job=\"cadvisor\"}' | jq -e '.data.result[0].value[1] == \"1\"'"

    run_test "Target app metrics available" \
        "curl -s '$PROMETHEUS_URL/api/v1/query?query=up{job=\"target-app\"}' | jq -e '.data.result[0].value[1] == \"1\"'"

    run_test "AI Agent metrics available" \
        "curl -s '$PROMETHEUS_URL/api/v1/query?query=up{job=\"aiops-agent\"}' | jq -e '.data.result[0].value[1] == \"1\"'"

    run_test "Agent memory overhead baseline" \
        "curl -s '$PROMETHEUS_URL/api/v1/query?query=container_memory_usage_bytes{name=\"aiops-agent\"}' | jq -e '.data.result[0].value[1] | tonumber < 134217728'"  # < 128MB
}

# ── Test 3: Alert Rules ───────────────────────────────────
test_alert_rules() {
    test_header "ALERT RULES VALIDATION"

    run_test "Alert rules loaded" \
        "curl -s '$PROMETHEUS_URL/api/v1/rules' | jq -e '.data.groups | length > 0'"

    run_test "CPU alert rule exists" \
        "curl -s '$PROMETHEUS_URL/api/v1/rules' | jq -e '.data.groups[].rules[] | select(.name == \"HighCPUUsage\")'"

    run_test "Memory alert rule exists" \
        "curl -s '$PROMETHEUS_URL/api/v1/rules' | jq -e '.data.groups[].rules[] | select(.name == \"HighMemoryUsage\")'"

    run_test "Request rate alert rule exists" \
        "curl -s '$PROMETHEUS_URL/api/v1/rules' | jq -e '.data.groups[].rules[] | select(.name == \"HighRequestRate\")'"

    run_test "System load alert rule exists" \
        "curl -s '$PROMETHEUS_URL/api/v1/rules' | jq -e '.data.groups[].rules[] | select(.name == \"HighSystemLoad\")'"
}

# ── Test 4: AI Agent Functionality ────────────────────────
test_ai_agent() {
    test_header "AI AGENT FUNCTIONALITY"

    # Test webhook endpoint with mock alert
    local mock_alert='{
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": "TestAlert",
                "severity": "warning",
                "scenario": "test"
            },
            "annotations": {
                "summary": "Test alert for validation",
                "description": "System validation test"
            },
            "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
        }]
    }'

    run_test "AI Agent webhook processes alerts" \
        "curl -s -X POST $AGENT_URL/webhook -H 'Content-Type: application/json' -d '$mock_alert' | jq -e 'length > 0'"

    run_test "AI Agent logs accessible" \
        "curl -s $AGENT_URL/logs | jq -e 'type == \"array\"'"

    run_test "AI Agent tools available" \
        "curl -s $AGENT_URL/health | jq -e '.gemini_configured'"
}

# ── Test 5: Scenario 1 - Overhead Baseline ──────────────
test_scenario_1() {
    test_header "SCENARIO 1: OVERHEAD BASELINE TEST"

    log "Measuring AI Agent overhead..."

    # Get baseline metrics
    local memory_usage=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=container_memory_usage_bytes{name=\"aiops-agent\"}" | jq -r '.data.result[0].value[1]')
    local cpu_usage=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=rate(container_cpu_usage_seconds_total{name=\"aiops-agent\"}[1m])*100" | jq -r '.data.result[0].value[1] // "0"')

    run_test "Agent memory usage < 200MB" \
        "[ $(echo \"$memory_usage < 209715200\" | bc) -eq 1 ]"

    run_test "Agent CPU usage < 10%" \
        "[ $(echo \"${cpu_usage:-0} < 10\" | bc) -eq 1 ]"

    log "Agent overhead: Memory=${memory_usage}B (~$((memory_usage/1024/1024))MB), CPU=${cpu_usage:-0}%"
}

# ── Test 6: Scenario 2 - DDoS Response ───────────────────
test_scenario_2() {
    test_header "SCENARIO 2: DDoS RESPONSE TEST"

    warn "Starting simulated DDoS scenario..."

    # Generate high request rate
    log "Generating high request rate..."
    for i in {1..50}; do
        curl -s "$TARGET_URL/" > /dev/null &
        curl -s "$TARGET_URL/heavy" > /dev/null &
    done
    wait

    sleep 5  # Allow metrics to collect

    # Check if high request rate is detected
    local request_rate=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=rate(flask_http_requests_total{job=\"target-app\"}[1m])" | jq -r '.data.result[0].value[1] // "0"')

    run_test "High request rate detected" \
        "[ $(echo \"${request_rate:-0} > 10\" | bc) -eq 1 ]"

    log "Request rate: ${request_rate:-0} req/s"

    # Trigger alert manually for testing
    local ddos_alert='{
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": "HighRequestRate",
                "severity": "critical",
                "scenario": "ddos"
            },
            "annotations": {
                "summary": "Request rate qua cao",
                "description": "Rate: 150 req/s"
            },
            "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
        }]
    }'

    curl -s -X POST "$AGENT_URL/webhook" -H 'Content-Type: application/json' -d "$ddos_alert" > /dev/null

    sleep 3  # Allow agent to process

    run_test "AI Agent responded to DDoS alert" \
        "curl -s '$AGENT_URL/logs?limit=5' | jq -e '.[] | select(.alert == \"HighRequestRate\")'"
}

# ── Test 7: Scenario 3 - CPU Stress Response ────────────
test_scenario_3() {
    test_header "SCENARIO 3: CPU STRESS RESPONSE TEST"

    warn "Starting CPU stress scenario..."

    # Start stress test
    log "Starting CPU stress in target container..."
    docker exec -d target-app stress-ng --cpu 2 --timeout 15s

    sleep 5  # Allow stress to build up

    # Check if high CPU is detected
    local cpu_usage=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=100-avg(rate(node_cpu_seconds_total{mode=\"idle\"}[1m]))*100" | jq -r '.data.result[0].value[1] // "0"')

    run_test "High CPU usage detected" \
        "[ $(echo \"${cpu_usage:-0} > 20\" | bc) -eq 1 ]"

    log "CPU usage: ${cpu_usage:-0}%"

    # Trigger CPU stress alert manually
    local cpu_alert='{
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": "HighCPUUsage",
                "severity": "critical",
                "scenario": "cpu_stress"
            },
            "annotations": {
                "summary": "CPU qua tai",
                "description": "CPU usage: 95%"
            },
            "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
        }]
    }'

    curl -s -X POST "$AGENT_URL/webhook" -H 'Content-Type: application/json' -d "$cpu_alert" > /dev/null

    sleep 5  # Allow agent to process and kill stress

    run_test "AI Agent responded to CPU stress alert" \
        "curl -s '$AGENT_URL/logs?limit=5' | jq -e '.[] | select(.alert == \"HighCPUUsage\")'"

    # Check if stress was killed (indirectly by checking if CPU dropped)
    sleep 10
    local cpu_after=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=100-avg(rate(node_cpu_seconds_total{mode=\"idle\"}[1m]))*100" | jq -r '.data.result[0].value[1] // "0"')

    log "CPU after remediation: ${cpu_after:-0}%"
}

# ── Test 8: Configuration Validation ─────────────────────
test_configuration() {
    test_header "CONFIGURATION VALIDATION"

    run_test "Environment variables loaded in agent" \
        "docker exec aiops-agent env | grep -q 'TARGET_CONTAINER_NAME=target-app'"

    run_test "Grafana dashboards provisioned" \
        "docker exec grafana ls /etc/grafana/provisioning/dashboards/ | grep -q 'aiops-overview.json'"

    run_test "Prometheus data source configured" \
        "docker exec grafana ls /etc/grafana/provisioning/datasources/ | grep -q 'prometheus.yml'"

    run_test "Alert rules configuration valid" \
        "docker exec prometheus /bin/promtool check rules /etc/prometheus/alert.rules.yml"
}

# ── Main execution ────────────────────────────────────────
main() {
    echo -e "${PURPLE}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║            AGENTIC AIOPS - SYSTEM VALIDATION             ║"
    echo "║                      NT531 Đồ Án                        ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # Prerequisites check
    if ! command -v jq &> /dev/null; then
        err "jq is required but not installed. Install with: apt-get install jq"
        exit 1
    fi

    if ! command -v bc &> /dev/null; then
        err "bc is required but not installed. Install with: apt-get install bc"
        exit 1
    fi

    # Run all test suites
    test_system_health
    test_metrics_collection
    test_alert_rules
    test_ai_agent
    test_configuration
    test_scenario_1
    test_scenario_2
    test_scenario_3

    # Results summary
    echo
    test_header "VALIDATION RESULTS"

    if [ $TESTS_FAILED -eq 0 ]; then
        ok "All $TESTS_PASSED tests passed! ✨"
        echo -e "${GREEN}System is fully functional and ready for demonstration.${NC}"
    else
        warn "$TESTS_PASSED/$TESTS_TOTAL tests passed, $TESTS_FAILED failed"
        echo -e "${YELLOW}Review failed tests and fix issues before demonstration.${NC}"
    fi

    echo
    log "Access URLs:"
    echo "  • Grafana:     $GRAFANA_URL (admin/admin123)"
    echo "  • Prometheus:  $PROMETHEUS_URL"
    echo "  • AlertManager: $ALERT_URL"
    echo "  • Agent Logs:  $AGENT_URL/logs"

    echo
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}✓ Ready for NT531 demonstration! 🚀${NC}"
        exit 0
    else
        exit $TESTS_FAILED
    fi
}

# Execute main function
main "$@"