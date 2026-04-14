#!/bin/bash

# Scenario 3: iptables Prometehus Exporter (Textfile Collector)
# Outputs metrics to /var/lib/node_exporter/textfile_collector/iptables.prom

METRICS_DIR="/var/lib/node_exporter/textfile_collector"
OUTPUT_FILE="$METRICS_DIR/iptables.prom"

# Create directory if it doesn't exist
mkdir -p "$METRICS_DIR"

echo "[INFO] Starting iptables exporter loop..."

while true; do
    # Get packet count for the rate limit rules
    # We look for lines in 'iptables -L -v' that contain our limit names or targets
    BLOCKED_PACKETS=$(sudo iptables -L INPUT -v -n | grep "DROP" | grep "tcp dpt:5000" | awk '{print $1}')
    RULE_COUNT=$(sudo iptables -L INPUT -n | grep "tcp dpt:5000" | wc -l)
    
    # Write to a temporary file then move (atomic)
    {
        echo "# HELP iptables_blocked_packets_total Total number of packets dropped by iptables for port 5000"
        echo "# TYPE iptables_blocked_packets_total counter"
        echo "iptables_blocked_packets_total ${BLOCKED_PACKETS:-0}"
        
        echo "# HELP iptables_rule_count Number of active iptables rules for port 5000"
        echo "# TYPE iptables_rule_count gauge"
        echo "iptables_rule_count ${RULE_COUNT:-0}"
    } > "${OUTPUT_FILE}.tmp"
    
    mv "${OUTPUT_FILE}.tmp" "$OUTPUT_FILE"
    
    # Wait for next scrape interval (10s as requested)
    sleep 10
done
