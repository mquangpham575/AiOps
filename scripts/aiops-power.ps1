# AiOps 3-Node Azure Cluster Power Control Script
# ==============================================================================
# Controls all 3 Azure VMs (Control, Load Gen, App)
# All infrastructure runs on Azure VMs - no local Docker required.
#
# Architecture:
#   Node 1 (Control): 10.0.1.4 - Prometheus, AlertManager, Grafana, AI Agent, Pushgateway
#   Node 2 (Load Gen): 10.0.1.5 - Locust, node-exporter, Pushgateway client
#   Node 3 (App): 10.0.1.6 - target-app, node-exporter, cAdvisor
#
# Usage:
#   .\aiops-power.ps1 start   - Start all 3 VMs and deploy infrastructure
#   .\aiops-power.ps1 stop    - Stop containers and deallocate VMs
#   .\aiops-power.ps1 status  - Check VM and service status

param (
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet("start", "stop", "status")]
    $Action,
    [ValidateSet("all", "control", "loadgen", "app")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"

# Fixed configuration for 3-node setup
$RG = "rg-aiops"
$SSH_KEY = Join-Path $PSScriptRoot "..\.ssh\aiops3_key_rsa"
$SSH_USER = "azureuser"
$REMOTE_PROJECT_DIR = "/home/azureuser/3rdY-Sem2"

# VM Configuration (using existing VMs)
$VMs = @{
    "control"  = @{ Name = "aiops-vm";       IP = "10.0.1.4"; PublicIP = "104.215.158.157" }
    "loadgen" = @{ Name = "aiops-loadgen-vm"; IP = "10.0.1.5"; PublicIP = "104.215.191.69" }
    "app"     = @{ Name = "aiops-app";        IP = "10.0.1.6"; PublicIP = "4.194.57.3" }
}

$SSH_COMMON_ARGS = @(
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ConnectTimeout=10",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=2"
)

function Test-WebHealth {
    param([string]$URL)
    try {
        $response = Invoke-WebRequest -Uri $URL -Method Head -TimeoutSec 3 -ErrorAction SilentlyContinue
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
    } catch {
        return $false
    }
}

function Test-SSHConnection {
    param([string]$IP)
    # Since SSH is often blocked, we use Test-NetConnection on the SSH port as a proxy
    $result = Test-NetConnection -ComputerName $IP -Port 22 -InformationLevel Quiet -ErrorAction SilentlyContinue
    return $result
}

function Get-SshKeyPath {
    if ($SSH_KEY.StartsWith("~/")) {
        return Join-Path $HOME $SSH_KEY.Substring(2)
    }
    return $SSH_KEY
}

function Start-VM {
    param([string]$Name, [string]$IP)

    Write-Host "  Starting $Name ($IP)..." -ForegroundColor Cyan
    az vm start -g $RG -n $Name --no-wait

    Write-Host "    Waiting for $Name to be running..." -ForegroundColor DarkGray
    az vm wait -g $RG -n $Name --created 2>$null
    Start-Sleep -Seconds 5
}

function Stop-VM {
    param([string]$Name)

    Write-Host "  Stopping $Name..." -ForegroundColor Yellow
    az vm deallocate -g $RG -n $Name --no-wait
}

function Deploy-Node {
    param(
        [string]$IP,
        [string]$ComposeFile,
        [string]$NodeName
    )

    $sshKeyPath = Get-SshKeyPath

    Write-Host "    Connecting to $NodeName ($IP)..." -ForegroundColor Cyan

    $deployScript = @"
set -e
cd $REMOTE_PROJECT_DIR

if [ ! -d ".git" ]; then
    echo 'Repo not found, cloning...'
    git clone https://github.com/nqt2512/3rdY-Sem2.git $REMOTE_PROJECT_DIR
    cd $REMOTE_PROJECT_DIR
else
    echo 'Updating repo...'
    cd $REMOTE_PROJECT_DIR
    git pull
fi

echo 'Building and starting containers...'
docker compose -f $ComposeFile up -d --build

echo 'Containers:'
docker compose -f $ComposeFile ps
"@

    $escapedScript = $deployScript -replace '([$"`])', '`$1'
    ssh @SSH_COMMON_ARGS -i $sshKeyPath "$SSH_USER@$IP" $escapedScript
}

function Stop-NodeContainers {
    param([string]$IP, [string]$ComposeFile)

    $sshKeyPath = Get-SshKeyPath
    ssh @SSH_COMMON_ARGS -i $sshKeyPath "$SSH_USER@$IP" "cd $REMOTE_PROJECT_DIR && docker compose -f $ComposeFile down" 2>$null
}

switch ($Action) {
    "start" {
        Write-Host "========================================" -ForegroundColor Green
        Write-Host " AIOps 3-Node Azure Cluster - START" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
        Write-Host ""

        if ($Target -eq "all" -or $Target -eq "control") {
            Write-Host "=== Starting Control Node (Node 1) ===" -ForegroundColor Cyan
            Start-VM -Name $VMs["control"].Name -IP $VMs["control"].IP
        }

        if ($Target -eq "all" -or $Target -eq "loadgen") {
            Write-Host "=== Starting Load Generator Node (Node 2) ===" -ForegroundColor Cyan
            Start-VM -Name $VMs["loadgen"].Name -IP $VMs["loadgen"].IP
        }

        if ($Target -eq "all" -or $Target -eq "app") {
            Write-Host "=== Starting App Node (Node 3) ===" -ForegroundColor Cyan
            Start-VM -Name $VMs["app"].Name -IP $VMs["app"].IP
        }

        Write-Host "`nWaiting for SSH to be ready..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 15

        if ($Target -eq "all" -or $Target -eq "control") {
            Write-Host "`n=== Deploying Control Node ===" -ForegroundColor Cyan
            Deploy-Node -IP $VMs["control"].IP -ComposeFile "ops/infra/docker-compose.control.yml" -NodeName "Control"
        }

        if ($Target -eq "all" -or $Target -eq "loadgen") {
            Write-Host "`n=== Deploying Load Generator Node ===" -ForegroundColor Cyan
            Deploy-Node -IP $VMs["loadgen"].IP -ComposeFile "ops/infra/docker-compose.loadgen.yml" -NodeName "Load Gen"
        }

        if ($Target -eq "all" -or $Target -eq "app") {
            Write-Host "`n=== Deploying App Node ===" -ForegroundColor Cyan
            Deploy-Node -IP $VMs["app"].IP -ComposeFile "ops/infra/docker-compose.app.yml" -NodeName "App"
        }

        Write-Host ""
        Write-Host "========================================" -ForegroundColor Green
        Write-Host " All nodes deployed successfully!" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Access URLs:" -ForegroundColor White
        Write-Host "  Grafana:       http://$($VMs['control'].IP):3000" -ForegroundColor Yellow
        Write-Host "  Prometheus:    http://$($VMs['control'].IP):9090" -ForegroundColor Yellow
        Write-Host "  AlertManager:  http://$($VMs['control'].IP):9093" -ForegroundColor Yellow
        Write-Host "  Pushgateway:   http://$($VMs['loadgen'].IP):9091" -ForegroundColor Yellow
        Write-Host "  Target App:    http://$($VMs['app'].IP):80" -ForegroundColor Yellow
        Write-Host "  cAdvisor:      http://$($VMs['app'].IP):8080" -ForegroundColor Yellow
    }

    "stop" {
        Write-Host "========================================" -ForegroundColor Yellow
        Write-Host " AIOps 3-Node Azure Cluster - STOP" -ForegroundColor Yellow
        Write-Host "========================================" -ForegroundColor Yellow
        Write-Host ""

        if ($Target -eq "all" -or $Target -eq "control") {
            Write-Host "=== Stopping containers on Control Node ===" -ForegroundColor Cyan
            Stop-NodeContainers -IP $VMs["control"].IP -ComposeFile "ops/infra/docker-compose.control.yml"
        }

        if ($Target -eq "all" -or $Target -eq "loadgen") {
            Write-Host "=== Stopping containers on Load Generator Node ===" -ForegroundColor Cyan
            Stop-NodeContainers -IP $VMs["loadgen"].IP -ComposeFile "ops/infra/docker-compose.loadgen.yml"
        }

        if ($Target -eq "all" -or $Target -eq "app") {
            Write-Host "=== Stopping containers on App Node ===" -ForegroundColor Cyan
            Stop-NodeContainers -IP $VMs["app"].IP -ComposeFile "ops/infra/docker-compose.app.yml"
        }

        Write-Host "`n=== Deallocating VMs ===" -ForegroundColor Yellow
        if ($Target -eq "all" -or $Target -eq "control") {
            Stop-VM -Name $VMs["control"].Name
        }
        if ($Target -eq "all" -or $Target -eq "loadgen") {
            Stop-VM -Name $VMs["loadgen"].Name
        }
        if ($Target -eq "all" -or $Target -eq "app") {
            Stop-VM -Name $VMs["app"].Name
        }

        Write-Host ""
        Write-Host "========================================" -ForegroundColor Green
        Write-Host " All nodes stopped and deallocated!" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
    }

    "status" {
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host " AIOps 3-Node Azure Cluster - STATUS" -ForegroundColor Cyan
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host ""

        Write-Host "Azure VM Status:" -ForegroundColor White
        az vm list -g $RG -d --query "[].{Name:name, State:powerState, IP:publicIps}" --output table 2>$null

        Write-Host "`nService Endpoints (Public Health Checks):" -ForegroundColor White
        
        # Test Control (AI Agent)
        $c_ip = $VMs['control'].PublicIP
        $agent_ok = Test-WebHealth -URL "http://$($c_ip):8083/health"
        $status = if ($agent_ok) { "ONLINE" } else { "OFFLINE (Wait for startup or check NSG)" }
        $color = if ($agent_ok) { "Green" } else { "Red" }
        Write-Host "  Control Node (AI Agent)   $($c_ip.PadRight(15)) [$status]" -ForegroundColor $color

        # Test App
        $a_ip = $VMs['app'].PublicIP
        $app_ok = Test-WebHealth -URL "http://$($a_ip):80/health"
        $status = if ($app_ok) { "ONLINE" } else { "OFFLINE (Wait for startup or check NSG)" }
        $color = if ($app_ok) { "Green" } else { "Red" }
        Write-Host "  App Node (Target App)     $($a_ip.PadRight(15)) [$status]" -ForegroundColor $color

        # Test LoadGen (Node Exporter as proxy for being alive)
        $l_ip = $VMs['loadgen'].PublicIP
        $lg_ok = Test-WebHealth -URL "http://$($l_ip):9100"
        $status = if ($lg_ok) { "ONLINE" } else { "OFFLINE (Wait for startup or check NSG)" }
        $color = if ($lg_ok) { "Green" } else { "Red" }
        Write-Host "  LoadGen Node (Metrics)    $($l_ip.PadRight(15)) [$status]" -ForegroundColor $color
    }
}
