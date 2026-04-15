# deploy-control.ps1 - Deploy Node 1: Control Plane
# SSH: azureuser@10.0.1.4
# Services: Prometheus, AlertManager, Grafana, Pushgateway, AI Agent, Rule-Based

param(
    [string]$RepoUrl = "https://github.com/nqt2512/3rdY-Sem2.git",
    [string]$RepoDir = "$env:TEMP\aiops-repo",
    [string]$SSHKey = "$PSScriptRoot\..\..\..\.ssh\aiops3_key"
)

$ErrorActionPreference = "Stop"

$VM_IP = "10.0.1.4"
$VM_USER = "azureuser"
$COMPOSE_FILE = "ops/infra/docker-compose.control.yml"

Write-Host "=== Deploying Control Node (Node 1) ===" -ForegroundColor Cyan
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

echo "=== Control Node deployed successfully ==="
echo "Grafana: http://$VM_IP:3000"
echo "Prometheus: http://$VM_IP:9090"
"@

$escapedScript = $script -replace '([$"`])', '`$1'

ssh -i "$SSHKey" -o StrictHostKeyChecking=no "$VM_USER@$VM_IP" $escapedScript
