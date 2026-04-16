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

    Write-Host "  Checking $Name ($IP)..." -ForegroundColor Cyan
    $vmInfo = az vm show -d -g $RG -n $Name --query "powerState" -o tsv 2>$null
    
    if ($vmInfo -eq "VM running") {
        Write-Host "    Already running. Skipping start." -ForegroundColor Green
        return
    }

    Write-Host "    Starting $Name..." -ForegroundColor Yellow
    az vm start -g $RG -n $Name --no-wait

    Write-Host "    Waiting for $Name to be running..." -ForegroundColor DarkGray
    az vm wait -g $RG -n $Name --created 2>$null
    Start-Sleep -Seconds 2
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

    echo "Synchronizing local files to remote ($NodeName)..."
    # Ensure remote directory exists
    ssh @SSH_COMMON_ARGS -i $sshKeyPath "$SSH_USER@$IP" "sudo mkdir -p $REMOTE_PROJECT_DIR && sudo chown -R $($SSH_USER):$($SSH_USER) $($REMOTE_PROJECT_DIR)"

    $localProjRoot = (Get-Item "$PSScriptRoot\..").FullName

    # Synchronize only necessary config directories (skip heavy terraform binaries)
    $remoteOpsDir = "$REMOTE_PROJECT_DIR/ops"
    ssh @SSH_COMMON_ARGS -i $sshKeyPath "$SSH_USER@$IP" "mkdir -p $remoteOpsDir/infra $remoteOpsDir/monitoring"
    
    scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i $sshKeyPath "$localProjRoot\ops\infra\*.yml" "$($SSH_USER)@$($IP):$remoteOpsDir/infra/"
    scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i $sshKeyPath -r "$localProjRoot\ops\monitoring" "$($SSH_USER)@$($IP):$remoteOpsDir/"
    scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i $sshKeyPath -r "$localProjRoot\src" "$($SSH_USER)@$($IP):$($REMOTE_PROJECT_DIR)"
    scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i $sshKeyPath "$localProjRoot\.env" "$($SSH_USER)@$($IP):$($REMOTE_PROJECT_DIR)"

    $pathParts = $ComposeFile -split '[/\\\\]'
    $remoteFile = $pathParts[-1]
    $remoteDir = $pathParts[0..($pathParts.Length - 2)] -join '/'

    $deployScript = @"
set -e
cd "$REMOTE_PROJECT_DIR"

echo "Cleaning up existing containers in $remoteDir..."
cd "$remoteDir"
sudo docker compose -p aiops down --remove-orphans || true
sudo docker rm -f pushgateway prometheus grafana alertmanager ai-agent rule-based-agent node-exporter cadvisor target-app || true

echo "Building and starting containers using $remoteFile..."
sudo docker compose -p aiops -f "$remoteFile" up -d --build

echo "Containers status:"
sudo docker compose -p aiops -f "$remoteFile" ps
"@

    $b64Script = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($deployScript))
    ssh @SSH_COMMON_ARGS -i $sshKeyPath "$SSH_USER@$IP" "echo $b64Script | base64 -d | sudo bash"
}

function Stop-NodeContainers {
    param([string]$IP, [string]$ComposeFile)

    $sshKeyPath = Get-SshKeyPath
    ssh @SSH_COMMON_ARGS -i $sshKeyPath "$SSH_USER@$IP" "cd $REMOTE_PROJECT_DIR && sudo docker compose -f $ComposeFile down" 2>$null
}

switch ($Action) {
    "start" {
        Write-Host "========================================" -ForegroundColor Green
        Write-Host " AIOps 3-Node Azure Cluster - START" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
        Write-Host ""

        if ($Target -eq "all" -or $Target -eq "control") {
            Write-Host "=== Starting Control Node (Node 1) ===" -ForegroundColor Cyan
            Start-VM -Name $VMs["control"].Name -IP $VMs["control"].PublicIP
        }

        if ($Target -eq "all" -or $Target -eq "loadgen") {
            Write-Host "=== Starting Load Generator Node (Node 2) ===" -ForegroundColor Cyan
            Start-VM -Name $VMs["loadgen"].Name -IP $VMs["loadgen"].PublicIP
        }

        if ($Target -eq "all" -or $Target -eq "app") {
            Write-Host "=== Starting App Node (Node 3) ===" -ForegroundColor Cyan
            Start-VM -Name $VMs["app"].Name -IP $VMs["app"].PublicIP
        }

        Write-Host "`nWaiting for SSH to be ready..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 15

        if ($Target -eq "all" -or $Target -eq "control") {
            Write-Host "`n=== Deploying Control Node ===" -ForegroundColor Cyan
            Deploy-Node -IP $VMs["control"].PublicIP -ComposeFile "ops/infra/docker-compose.control.yml" -NodeName "Control"
        }

        if ($Target -eq "all" -or $Target -eq "loadgen") {
            Write-Host "`n=== Deploying Load Generator Node ===" -ForegroundColor Cyan
            Deploy-Node -IP $VMs["loadgen"].PublicIP -ComposeFile "ops/infra/docker-compose.loadgen.yml" -NodeName "Load Gen"
        }

        if ($Target -eq "all" -or $Target -eq "app") {
            Write-Host "`n=== Deploying App Node ===" -ForegroundColor Cyan
            Deploy-Node -IP $VMs["app"].PublicIP -ComposeFile "ops/infra/docker-compose.app.yml" -NodeName "App"
        }

        Write-Host ""
        Write-Host "========================================" -ForegroundColor Green
        Write-Host " All nodes deployed successfully!" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Access URLs:" -ForegroundColor White
        Write-Host "  Grafana:       http://$($VMs['control'].PublicIP):3000" -ForegroundColor Yellow
        Write-Host "  AI Agent:      http://$($VMs['control'].PublicIP):8083/logs/ui" -ForegroundColor Yellow
        Write-Host "  Prometheus:    http://$($VMs['control'].PublicIP):9090" -ForegroundColor Yellow
        Write-Host "  Pushgateway:   http://$($VMs['control'].PublicIP):9091" -ForegroundColor Yellow
        Write-Host "  Target App:    http://$($VMs['app'].PublicIP):80/health" -ForegroundColor Yellow
        Write-Host "  cAdvisor:      http://$($VMs['app'].PublicIP):8080" -ForegroundColor Yellow
    }

    "stop" {
        Write-Host "========================================" -ForegroundColor Yellow
        Write-Host " AIOps 3-Node Azure Cluster - STOP" -ForegroundColor Yellow
        Write-Host "========================================" -ForegroundColor Yellow
        Write-Host ""

        if ($Target -eq "all" -or $Target -eq "control") {
            Write-Host "=== Stopping containers on Control Node ===" -ForegroundColor Cyan
            Stop-NodeContainers -IP $VMs["control"].PublicIP -ComposeFile "ops/infra/docker-compose.control.yml"
        }

        if ($Target -eq "all" -or $Target -eq "loadgen") {
            Write-Host "=== Stopping containers on Load Generator Node ===" -ForegroundColor Cyan
            Stop-NodeContainers -IP $VMs["loadgen"].PublicIP -ComposeFile "ops/infra/docker-compose.loadgen.yml"
        }

        if ($Target -eq "all" -or $Target -eq "app") {
            Write-Host "=== Stopping containers on App Node ===" -ForegroundColor Cyan
            Stop-NodeContainers -IP $VMs["app"].PublicIP -ComposeFile "ops/infra/docker-compose.app.yml"
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
        Write-Host "`n=== AIOps Cluster Status ===" -ForegroundColor Cyan
        
        # Pre-fetch VM states
        $vmData = az vm list -g $RG -d --query "[].{name:name, state:powerState}" --output json | ConvertFrom-Json
        
        $results = @()
        $nodeKeys = @("control", "loadgen", "app")
        
        foreach ($key in $nodeKeys) {
            $vmConfig = $VMs[$key]
            $ip = $vmConfig.PublicIP
            
            # Find state
            $match = $vmData | Where-Object { $_.name -eq $vmConfig.Name }
            $stateTxt = if ($match) { $match.state -replace "VM ", "" } else { "Unknown" }
            
            # Health check
            $url = switch ($key) {
                "control" { "http://$($ip):8083/health" }
                "app"     { "http://$($ip):80/health" }
                "loadgen" { "http://$($ip):9100" }
            }
            
            $isOnline = Test-WebHealth -URL $url
            $healthStatus = if ($isOnline) { "ONLINE" } else { "OFFLINE" }
            
            $results += [PSCustomObject]@{
                NODE      = $key.ToUpper()
                STATE     = $stateTxt
                IP        = $ip
                HEALTH    = $healthStatus
            }
        }
        
        $results | Format-Table -AutoSize
        Write-Host ""
    }
}
