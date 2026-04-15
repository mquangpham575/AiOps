# deploy-app.ps1 - Deploy Node 3: Target Application
# SSH: azureuser@10.0.1.6
# Services: target-app, node-exporter, cAdvisor

param(
    [string]$RepoUrl = "https://github.com/nqt2512/3rdY-Sem2.git",
    [string]$RepoDir = "$env:TEMP\aiops-repo",
    [string]$SSHKey = "$PSScriptRoot\..\..\..\.ssh\aiops3_key"
)

$ErrorActionPreference = "Stop"

$VM_IP = "10.0.1.6"
$VM_USER = "azureuser"
$COMPOSE_FILE = "ops/infra/docker-compose.app.yml"

Write-Host "=== Deploying Target App Node (Node 3) ===" -ForegroundColor Cyan
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

echo "=== Target App Node deployed successfully ==="
echo "Target App: http://$VM_IP:80"
echo "cAdvisor: http://$VM_IP:8080"
echo "Node Exporter: http://$VM_IP:9100"
"@

$escapedScript = $script -replace '([$"`])', '`$1'

ssh -i "$SSHKey" -o StrictHostKeyChecking=no "$VM_USER@$VM_IP" $escapedScript
