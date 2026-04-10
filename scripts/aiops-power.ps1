# AiOps Distributed Cluster Power Control Script
# Provides start/stop/status actions for both the Azure VM and Local Docker containers.

param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("start", "stop", "status")]
    $Action
)

$RG = "rg-aiops"
$VM_NAME = "aiops-vm"

# Fix: Ensure we are always pointing to the project root (one level up from /scripts)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot

# IMPORTANT: Clear DOCKER_HOST to ensure we check LOCAL docker first
$env:DOCKER_HOST = ""

# Load and parse .env properly
if (-not (Test-Path ".env")) { Write-Error "❌ Could not find .env file in project root ($ProjectRoot)!"; exit }
$envFile = Get-Content ".env"

$azureIpLine = $envFile | Select-String "^AZURE_VM_IP="
if ($null -eq $azureIpLine) { Write-Error "❌ AZURE_VM_IP not found in .env"; exit }
$global:azureIp = $azureIpLine.ToString().Split("=")[1].Trim()

if ([string]::IsNullOrWhiteSpace($global:azureIp) -or $global:azureIp -eq "127.0.0.1") {
    Write-Warning "⚠️ AZURE_VM_IP is empty or set to 127.0.0.1. Please update your .env file with the actual Azure VM IP."
}

# Check if local Docker is running
docker info >$null 2>&1
if ($LastExitCode -ne 0) {
    Write-Error "❌ Docker Desktop is NOT running on your local PC. Please start Docker Desktop and truy cập lại."
    exit
}

switch ($Action) {
    "start" {
        Write-Host "🚀 Checking Azure VM ($VM_NAME) in RG ($RG)..." -ForegroundColor Cyan
        $vmExists = az vm show -g $RG -n $VM_NAME --query "name" -o tsv 2>$null
        if ($null -eq $vmExists) {
            Write-Error "❌ Could not find VM '$VM_NAME' in Resource Group '$RG'."
            Write-Host "🔍 Your available VMs are:" -ForegroundColor Yellow
            az vm list --query "[].{Name:name, ResourceGroup:resourceGroup}" --output table
            Write-Host "👉 Please update the `$RG` and `$VM_NAME` variables in this script." -ForegroundColor Yellow
            exit
        }

        Write-Host "🚀 Starting Azure VM ($VM_NAME)..." -ForegroundColor Cyan
        az vm start -g $RG -n $VM_NAME
        
        if ([string]::IsNullOrWhiteSpace($global:azureIp)) {
            Write-Error "❌ AZURE_VM_IP is missing in .env. Cannot connect to remote Docker."
            exit
        }

        Write-Host "📡 Connecting to Docker at $global:azureIp and starting Application Plane..." -ForegroundColor Cyan
        $env:DOCKER_HOST = "tcp://$global:azureIp:2375"
        docker -H "tcp://$global:azureIp:2375" compose -f docker-compose.app.yml up -d --build
        
        Write-Host "⚙️ Generating dynamic prometheus.yml..." -ForegroundColor Cyan
        (Get-Content config\prometheus\prometheus.yml.template) -replace '\$\{AZURE_VM_IP\}', $global:azureIp | Set-Content config\prometheus\prometheus.yml

        Write-Host "📦 Starting Control Plane (Local PC)..." -ForegroundColor Cyan
        $env:DOCKER_HOST = ""
        docker compose -f docker-compose.control.yml up -d --build
        
        Write-Host "✅ System started. Access Grafana at http://localhost:3000" -ForegroundColor Green
    }
    
    "stop" {
        Write-Host "🛑 Stopping Local Control Plane..." -ForegroundColor Yellow
        docker compose -f docker-compose.control.yml down
        
        Write-Host "🛑 Stopping Remote Application Plane..." -ForegroundColor Yellow
        docker -H "tcp://$global:azureIp:2375" compose -f docker-compose.app.yml down
        
        Write-Host "💤 Deallocating Azure VM to save credits..." -ForegroundColor Yellow
        az vm deallocate -g $RG -n $VM_NAME
        
        Write-Host "✅ System off and VM deallocated." -ForegroundColor Green
    }
    
    "status" {
        Write-Host "🔍 Azure VM Power Status:" -ForegroundColor Cyan
        az vm list -g $RG -d --query "[].{Name:name, State:powerState}" --output table
        
        Write-Host "`n🔍 Local Docker Status:" -ForegroundColor Cyan
        docker compose -f docker-compose.control.yml ps
    }
}
