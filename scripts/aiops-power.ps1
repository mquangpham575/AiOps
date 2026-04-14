# AiOps Distributed Cluster Power Control Script
# Provides start/stop/status actions for both the Azure VM and Local Docker containers.
# Docker access to the Azure VM uses SSH tunnels (no TCP :2375 exposure).

param (
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet("start", "stop", "status")]
    $Action
)

$RG = "rg-aiops"
$APP_VM_NAME = "aiops-vm"
$LOADGEN_VM_NAME = "aiops-loadgen-vm"
$SSH_KEY = "~/.ssh/aiops_key"
$SSH_USER = "azureuser"
$REMOTE_PROJECT_DIR = "/home/azureuser/DoAn"
$TUNNEL_STATE_FILE = "$env:TEMP\aiops-docker-tunnel.state"
$SSH_COMMON_ARGS = @(
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ConnectTimeout=10",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=2"
)

# Fix: Ensure we are always pointing to the project root (one level up from /scripts)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot

# IMPORTANT: Clear DOCKER_HOST to ensure we check LOCAL docker first
$env:DOCKER_HOST = ""

# Load and parse .env properly
if (-not (Test-Path ".env")) { Write-Error "Could not find .env file in project root ($ProjectRoot)!"; exit }
$envFile = Get-Content ".env"

$azureAppIpLine = $envFile | Select-String "^AZURE_APP_IP="
if ($null -eq $azureAppIpLine) { Write-Error "AZURE_APP_IP not found in .env"; exit }
$global:azureAppIp = $azureAppIpLine.ToString().Split("=")[1].Trim()

$azureLoadgenIpLine = $envFile | Select-String "^AZURE_LOADGEN_IP="
if ($azureLoadgenIpLine) {
    $global:azureLoadgenIp = $azureLoadgenIpLine.ToString().Split("=")[1].Trim()
}

$rgLine = $envFile | Select-String "^AZURE_RESOURCE_GROUP="
if ($rgLine) {
    $RG = $rgLine.ToString().Split("=")[1].Trim()
}

$vmLine = $envFile | Select-String "^AZURE_VM_NAME="
if ($vmLine) {
    $APP_VM_NAME = $vmLine.ToString().Split("=")[1].Trim()
}

$loadgenVmLine = $envFile | Select-String "^AZURE_LOADGEN_VM_NAME="
if ($loadgenVmLine) {
    $LOADGEN_VM_NAME = $loadgenVmLine.ToString().Split("=")[1].Trim()
}

$sshUserLine = $envFile | Select-String "^AZURE_SSH_USER="
if ($sshUserLine) {
    $SSH_USER = $sshUserLine.ToString().Split("=")[1].Trim()
}

$sshKeyLine = $envFile | Select-String "^AZURE_SSH_KEY_PATH="
if ($sshKeyLine) {
    $SSH_KEY = $sshKeyLine.ToString().Split("=")[1].Trim()
}

if ([string]::IsNullOrWhiteSpace($global:azureAppIp) -or $global:azureAppIp -eq "127.0.0.1") {
    Write-Warning "AZURE_APP_IP is empty or set to 127.0.0.1. Please update your .env file with the actual Application VM IP."
}
if ([string]::IsNullOrWhiteSpace($global:azureLoadgenIp)) {
    Write-Warning "AZURE_LOADGEN_IP is empty. Please update your .env file with the actual Loadgen VM IP."
}

# Check if local Docker is running (Helper function)
function Test-DockerRunning {
    docker info >$null 2>&1
    return ($LastExitCode -eq 0)
}

function Get-SshKeyPath {
    if ($SSH_KEY.StartsWith("~/")) {
        return Join-Path $HOME $SSH_KEY.Substring(2)
    }
    return $SSH_KEY
}

function Test-DockerTunnelRunning {
    if (-not (Test-Path $TUNNEL_STATE_FILE)) {
        return $false
    }

    $tunnelProcessIdRaw = Get-Content $TUNNEL_STATE_FILE -ErrorAction SilentlyContinue
    if (-not $tunnelProcessIdRaw) {
        Remove-Item $TUNNEL_STATE_FILE -Force -ErrorAction SilentlyContinue
        return $false
    }

    $tunnelProcessId = 0
    if (-not [int]::TryParse(($tunnelProcessIdRaw | Select-Object -First 1).Trim(), [ref]$tunnelProcessId)) {
        Remove-Item $TUNNEL_STATE_FILE -Force -ErrorAction SilentlyContinue
        return $false
    }

    $runningSshProc = Get-Process -Id $tunnelProcessId -ErrorAction SilentlyContinue
    if (-not $runningSshProc -or $runningSshProc.ProcessName -ne "ssh") {
        Remove-Item $TUNNEL_STATE_FILE -Force -ErrorAction SilentlyContinue
        return $false
    }

    return $true
}

# Start an SSH tunnel for Docker socket forwarding
function Start-DockerTunnel {
    if (Test-DockerTunnelRunning) {
        $activeTunnelState = Get-Content $TUNNEL_STATE_FILE
        Write-Host "  SSH tunnel already active (process: $activeTunnelState)" -ForegroundColor DarkGray
        return
    }

    $sshKeyPath = Get-SshKeyPath
    if (-not (Test-Path $sshKeyPath)) {
        Write-Error "SSH private key not found at '$sshKeyPath'."
        exit 1
    }

    Write-Host "  Opening SSH tunnel for Docker socket to App VM..." -ForegroundColor Cyan
    $portInUse = Get-NetTCPConnection -LocalPort 2375 -ErrorAction SilentlyContinue
    if ($portInUse -and -not (Test-DockerTunnelRunning)) {
        Write-Error "Local port 2375 is already in use by another process. Free the port or stop the other tunnel first."
        exit 1
    }

    $sshArgs = @()
    $sshArgs += $SSH_COMMON_ARGS
    $sshArgs += @("-o", "ExitOnForwardFailure=yes", "-i", $sshKeyPath, "-N", "-L", "2375:/var/run/docker.sock", "$SSH_USER@$global:azureAppIp")
    $tunnelProcess = Start-Process -NoNewWindow -PassThru -FilePath ssh -ArgumentList $sshArgs
    $tunnelProcess.Id | Out-File -FilePath $TUNNEL_STATE_FILE -Force
    Start-Sleep -Seconds 2

    if (-not (Test-DockerTunnelRunning)) {
        Write-Error "SSH tunnel failed to start. Check SSH access and key permissions."
        exit 1
    }

    Write-Host "  SSH tunnel active (process: $($tunnelProcess.Id))" -ForegroundColor Green
}

# Stop the SSH tunnel
function Stop-DockerTunnel {
    if (Test-Path $TUNNEL_STATE_FILE) {
        try {
            $tunnelProcessIdRaw = Get-Content $TUNNEL_STATE_FILE -ErrorAction SilentlyContinue
            $tunnelProcessId = 0
            if ([int]::TryParse(($tunnelProcessIdRaw | Select-Object -First 1).Trim(), [ref]$tunnelProcessId)) {
                $runningSshProc = Get-Process -Id $tunnelProcessId -ErrorAction SilentlyContinue
                if ($runningSshProc -and $runningSshProc.ProcessName -eq "ssh") {
                    Stop-Process -Id $tunnelProcessId -Force -ErrorAction SilentlyContinue
                    Write-Host "  SSH tunnel stopped" -ForegroundColor Yellow
                } else {
                    Write-Host "  Tunnel PID file stale; no matching ssh process" -ForegroundColor DarkGray
                }
            } else {
                Write-Host "  Tunnel PID file invalid; removing state file" -ForegroundColor DarkGray
            }
        } catch {
            Write-Host "  SSH tunnel already stopped" -ForegroundColor DarkGray
        }
        Remove-Item $TUNNEL_STATE_FILE -Force
    }
}

switch ($Action) {
    "start" {
        $DockerReady = Test-DockerRunning
        if (-not $DockerReady) {
            Write-Warning "Docker Desktop is NOT running. The Local Control Plane and Remote Containers will NOT be started."
        }
        
        Write-Host "Starting Azure VMs in RG ($RG)..." -ForegroundColor Cyan
        foreach ($vm in @($APP_VM_NAME, $LOADGEN_VM_NAME)) {
            Write-Host "  Starting $vm..." -ForegroundColor Cyan
            az vm start -g $RG -n $vm --no-wait
        }
        Write-Host "Waiting for VMs to initialize..." -ForegroundColor DarkGray
        az vm wait -g $RG -n $APP_VM_NAME --created
        az vm wait -g $RG -n $LOADGEN_VM_NAME --created
        Start-Sleep -Seconds 10 # Extra buffer for SSH

        if ($DockerReady) {
            $sshKeyPath = Get-SshKeyPath
            
            Write-Host "Deploying Application Plane -> $APP_VM_NAME ($global:azureAppIp)..." -ForegroundColor Cyan
            ssh @SSH_COMMON_ARGS -i $sshKeyPath "$SSH_USER@$global:azureAppIp" "cd $REMOTE_PROJECT_DIR && docker compose -f ops/infra/docker-compose.app.yml up -d --build"

            Write-Host "Deploying Loadgen/Observability Plane -> $LOADGEN_VM_NAME ($global:azureLoadgenIp)..." -ForegroundColor Cyan
            ssh @SSH_COMMON_ARGS -i $sshKeyPath "$SSH_USER@$global:azureLoadgenIp" "cd $REMOTE_PROJECT_DIR && docker compose -f ops/infra/docker-compose.loadgen.yml up -d --build"

            Write-Host "Generating dynamic prometheus.yml..." -ForegroundColor Cyan
            (Get-Content ops\monitoring\prometheus\prometheus.yml.template) `
                -replace '\$\{AZURE_APP_IP\}', $global:azureAppIp `
                -replace '\$\{AZURE_LOADGEN_IP\}', $global:azureLoadgenIp `
                | Set-Content ops\monitoring\prometheus\prometheus.yml

            Start-DockerTunnel

            Write-Host "Starting Control Plane (Local PC)..." -ForegroundColor Cyan
            docker compose -f ops/infra/docker-compose.control.yml up -d --build

            Write-Host "System fully started." -ForegroundColor Green
            Write-Host "  App: http://$global:azureAppIp" -ForegroundColor DarkGray
            Write-Host "  Grafana: http://$global:azureLoadgenIp:3000" -ForegroundColor DarkGray
        } else {
            Write-Host "Azure VMs are powering on. Please start Docker Desktop later and re-run this script to launch planes." -ForegroundColor Yellow
        }
    }

    "stop" {
        if (Test-DockerRunning) {
            Write-Host "Stopping Local Control Plane..." -ForegroundColor Yellow
            docker compose -f ops/infra/docker-compose.control.yml down
        }

        Stop-DockerTunnel

        $sshKeyPath = Get-SshKeyPath
        Write-Host "Stopping Remote Planes..." -ForegroundColor Yellow
        ssh @SSH_COMMON_ARGS -i $sshKeyPath "$SSH_USER@$global:azureAppIp" "cd $REMOTE_PROJECT_DIR && docker compose -f ops/infra/docker-compose.app.yml down" 2>$null
        ssh @SSH_COMMON_ARGS -i $sshKeyPath "$SSH_USER@$global:azureLoadgenIp" "cd $REMOTE_PROJECT_DIR && docker compose -f ops/infra/docker-compose.loadgen.yml down" 2>$null

        Write-Host "Deallocating Azure VMs..." -ForegroundColor Yellow
        foreach ($vm in @($APP_VM_NAME, $LOADGEN_VM_NAME)) {
            az vm deallocate -g $RG -n $vm --no-wait
        }
        Write-Host "System off and VMs deallocating." -ForegroundColor Green
    }

    "status" {
        Write-Host "Azure VM Power Status:" -ForegroundColor Cyan
        az vm list -g $RG -d --query "[].{Name:name, State:powerState, IP:publicIps}" --output table

        Write-Host "`nLocal Docker Status:" -ForegroundColor Cyan
        if (Test-DockerRunning) {
            docker compose -f ops/infra/docker-compose.control.yml ps
        } else {
            Write-Host "  Docker Desktop not running" -ForegroundColor Yellow
        }

        Write-Host "`nSSH Tunnel Status:" -ForegroundColor Cyan
        if (Test-DockerTunnelRunning) {
            Write-Host "  Active -> $APP_VM_NAME" -ForegroundColor Green
        } else {
            Write-Host "  Not running" -ForegroundColor DarkGray
        }
    }
}
