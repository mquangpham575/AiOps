# AiOps Distributed Cluster Power Control Script
# Provides start/stop/status actions for both the Azure VM and Local Docker containers.

param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("start", "stop", "status")]
    $Action
)

$RG = "rg-aiops"
$VM_NAME = "aiops-vm"
$AZURE_IP = "104.215.158.157"

switch ($Action) {
    "start" {
        Write-Host "🚀 Starting Azure VM ($VM_NAME)..." -ForegroundColor Cyan
        az vm start -g $RG -n $VM_NAME
        
        Write-Host "📡 Connecting to Docker and starting Application Plane..." -ForegroundColor Cyan
        $env:DOCKER_HOST = "tcp://$AZURE_IP:2375"
        docker compose -f docker-compose.app.yml up -d --build
        
        Write-Host "📦 Starting Control Plane (Local PC)..." -ForegroundColor Cyan
        $env:DOCKER_HOST = ""
        docker compose -f docker-compose.control.yml up -d --build
        
        Write-Host "✅ System started. Access Grafana at http://localhost:3000" -ForegroundColor Green
    }
    
    "stop" {
        Write-Host "🛑 Stopping Local Control Plane..." -ForegroundColor Yellow
        docker compose -f docker-compose.control.yml down
        
        Write-Host "🛑 Stopping Remote Application Plane..." -ForegroundColor Yellow
        $env:DOCKER_HOST = "tcp://$AZURE_IP:2375"
        docker compose -f docker-compose.app.yml down
        
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
