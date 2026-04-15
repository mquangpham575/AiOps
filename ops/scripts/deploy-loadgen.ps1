# deploy-loadgen.ps1 - Deploy Node 2: Load Generator
# SSH: azureuser@10.0.1.5
# Services: node-exporter, Pushgateway (Locust runs on host)

param(
    [string]$RepoUrl = "https://github.com/nqt2512/3rdY-Sem2.git",
    [string]$RepoDir = "$env:TEMP\aiops-repo",
    [string]$SSHKey = "$PSScriptRoot\..\..\..\.ssh\aiops3_key"
)

$ErrorActionPreference = "Stop"

$VM_IP = "10.0.1.5"
$VM_USER = "azureuser"
$COMPOSE_FILE = "ops/infra/docker-compose.loadgen.yml"

Write-Host "=== Deploying Load Generator Node (Node 2) ===" -ForegroundColor Cyan
Write-Host "VM: $VM_USER@$VM_IP"

$script = @"
set -e

# Clone or update repo
if [ -d "$RepoDir" ]; then
    cd $RepoDir && git pull
else
    git clone $RepoUrl $RepoDir
    cd $RepoDir
fi

# Ensure Docker is running
sudo systemctl start docker 2>/dev/null || true

# Deploy infrastructure
cd $RepoDir
docker compose -f $COMPOSE_FILE up -d --build

# Verify services
echo "=== Running containers ==="
docker compose -f $COMPOSE_FILE ps

echo "=== Load Generator Node deployed successfully ==="
echo "Pushgateway: http://$VM_IP:9091"
echo "Node Exporter: http://$VM_IP:9100"
echo ""
echo "To run Locust tests:"
echo "  ATTACK_PROFILE=baseline locust -f tests/performance/locustfile.py --host=http://10.0.1.6:80 --run-time 300s --headless --tags baseline"
"@

$escapedScript = $script -replace '([$"`])', '`$1'

ssh -i "$SSHKey" -o StrictHostKeyChecking=no "$VM_USER@$VM_IP" $escapedScript
