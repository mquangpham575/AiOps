# deploy-all.ps1 - Deploy all 3 nodes sequentially
# Deploys: Node 1 (Control) -> Node 2 (Load Gen) -> Node 3 (App)

param(
    [string]$RepoUrl = "https://github.com/nqt2512/3rdY-Sem2.git",
    [string]$SSHKey = "$PSScriptRoot\..\..\..\.ssh\aiops3_key"
)

$ErrorActionPreference = "Stop"

$RepoDir = "$env:TEMP\aiops-repo"

Write-Host "========================================" -ForegroundColor Green
Write-Host " AIOps 3-Node Azure Deployment" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

function Deploy-Node {
    param(
        [string]$Name,
        [string]$IP,
        [string]$ComposeFile,
        [string[]]$Endpoints
    )

    Write-Host "=== Deploying $Name ($IP) ===" -ForegroundColor Cyan

    $script = @"
set -e
cd $RepoDir
docker compose -f $ComposeFile up -d --build
docker compose -f $ComposeFile ps
"@

    $escapedScript = $script -replace '([$"`])', '`$1'

    ssh -i "$SSHKey" -o StrictHostKeyChecking=no "azureuser@$IP" $escapedScript

    Write-Host "$Name deployed successfully!" -ForegroundColor Green
    foreach ($ep in $Endpoints) {
        Write-Host "  - $ep" -ForegroundColor Yellow
    }
    Write-Host ""
}

# Pre-flight: clone repo to temp location (will be used by all nodes)
Write-Host "=== Cloning repository to $RepoDir ===" -ForegroundColor Cyan
ssh -i "$SSHKey" -o StrictHostKeyChecking=no "azureuser@10.0.1.4" @"
set -e
if [ -d "$RepoDir" ]; then
    cd $RepoDir && git pull
else
    git clone $RepoUrl $RepoDir
fi
"@

# Deploy Node 1: Control Plane
Deploy-Node -Name "Node 1: Control" -IP "10.0.1.4" -ComposeFile "ops/infra/docker-compose.control.yml" -Endpoints @(
    "Grafana: http://10.0.1.4:3000",
    "Prometheus: http://10.0.1.4:9090",
    "AlertManager: http://10.0.1.4:9093"
)

# Deploy Node 2: Load Generator
Deploy-Node -Name "Node 2: Load Gen" -IP "10.0.1.5" -ComposeFile "ops/infra/docker-compose.loadgen.yml" -Endpoints @(
    "Pushgateway: http://10.0.1.5:9091",
    "Node Exporter: http://10.0.1.5:9100"
)

# Deploy Node 3: Target App
Deploy-Node -Name "Node 3: Target App" -IP "10.0.1.6" -ComposeFile "ops/infra/docker-compose.app.yml" -Endpoints @(
    "Target App: http://10.0.1.6:80",
    "cAdvisor: http://10.0.1.6:8080",
    "Node Exporter: http://10.0.1.6:9100"
)

Write-Host "========================================" -ForegroundColor Green
Write-Host " All 3 nodes deployed successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Quick access:" -ForegroundColor White
Write-Host "  Grafana:     http://10.0.1.4:3000" -ForegroundColor Yellow
Write-Host "  Prometheus:  http://10.0.1.4:9090" -ForegroundColor Yellow
Write-Host "  Target App:  http://10.0.1.6:80" -ForegroundColor Yellow
