#!/bin/bash

# Scenario 3: iptables Rate Limiting Control
LIMIT=100
CLEAR=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --limit) LIMIT="$2"; shift ;;
        --clear) CLEAR=true ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

if [ "$CLEAR" = true ]; then
    echo "[ACTION] Clearing all custom iptables rate limits..."
    sudo iptables -D INPUT -p tcp --dport 5000 -m hashlimit --hashlimit-name http_limit -j ACCEPT 2>/dev/null
    sudo iptables -D INPUT -p tcp --dport 5000 -j DROP 2>/dev/null
    echo "[RESULT] Rules cleared."
    exit 0
fi

TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
echo "[ACTION] Setting iptables rate limit to $LIMIT req/s/IP at $TIMESTAMP"

# 1. Allow traffic up to the limit per source IP
# --hashlimit-upto: max average rate
# --hashlimit-burst: initial burst size
sudo iptables -A INPUT -p tcp --dport 5000 \
    -m hashlimit --hashlimit-upto $LIMIT/sec \
    --hashlimit-burst 5 \
    --hashlimit-mode srcip \
    --hashlimit-name http_limit_$LIMIT \
    -j ACCEPT

# 2. Drop everything else (that exceeds the limit) for this port
sudo iptables -A INPUT -p tcp --dport 5000 -j DROP

echo "[RESULT] Rate limit applied successfully."
