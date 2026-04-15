# setup-ssh-tunnel.ps1 - Create SSH tunnels to Azure VMs
# ==============================================================================
# Purpose: Access services on Azure VMs from local machine
# Usage:
#   .\setup-ssh-tunnel.ps1                    # Interactive menu
#   .\setup-ssh-tunnel.ps1 -Service grafana   # Connect to specific service
#   .\setup-ssh-tunnel.ps1 -All               # Connect to all services

param(
    [ValidateSet("grafana", "prometheus", "pushgateway", "cadvisor", "all")]
    [string]$Service = "",
    [switch]$All,
    [string]$SSHKey = "$PSScriptRoot\..\..\..\.ssh\aiops3_key_rsa"
)

$ErrorActionPreference = "Stop"

# VM Configuration
$VM_USER = "azureuser"
$VM_IPS = @{
    "control"  = "10.0.1.4"
    "loadgen"  = "10.0.1.5"
    "app"      = "10.0.1.6"
}

# Service ports mapping
$Services = @{
    "grafana"    = @{ Host = "control";  LocalPort = 3000; RemotePort = 3000; Desc = "Grafana Dashboard" }
    "prometheus" = @{ Host = "control";  LocalPort = 9090; RemotePort = 9090; Desc = "Prometheus UI" }
    "alertmanager" = @{ Host = "control"; LocalPort = 9093; RemotePort = 9093; Desc = "AlertManager" }
    "pushgateway" = @{ Host = "loadgen"; LocalPort = 9091; RemotePort = 9091; Desc = "Pushgateway" }
    "cadvisor"  = @{ Host = "app";      LocalPort = 8080; RemotePort = 8080; Desc = "cAdvisor" }
    "app"       = @{ Host = "app";      LocalPort = 80;   RemotePort = 80;   Desc = "Target App" }
}

function Start-SSHTunnel {
    param(
        [string]$HostIP,
        [string]$LocalPort,
        [string]$RemotePort,
        [string]$ServiceName
    )

    $sshCmd = "ssh -i `"$SSHKey`" -L ${LocalPort}:localhost:${RemotePort} -N -f ${VM_USER}@${HostIP}"
    Write-Host "Starting tunnel: ${ServiceName} (localhost:${LocalPort} -> ${HostIP}:${RemotePort})" -ForegroundColor Cyan

    $process = Start-Process -FilePath "ssh" -ArgumentList "-i", "`"$SSHKey`"", "-L", "${LocalPort}:localhost:${RemotePort}", "-N", "-f", "${VM_USER}@${HostIP}" -PassThru -WindowStyle Hidden

    if ($process) {
        Write-Host "[OK] ${ServiceName} tunnel active on port ${LocalPort}" -ForegroundColor Green
        return $process.Id
    } else {
        Write-Host "[FAIL] ${ServiceName} tunnel failed" -ForegroundColor Red
        return $null
    }
}

function Show-Menu {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host " AIOps Azure SSH Tunnels" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Available services:" -ForegroundColor White
    Write-Host ""
    $i = 1
    foreach ($svc in $Services.Keys | Sort-Object) {
        $info = $Services[$svc]
        Write-Host "  $($i). $($svc.PadRight(15)) -> $($info.Host) (:$($info.RemotePort))  [$($info.Desc)]"
        $i++
    }
    Write-Host ""
    Write-Host "  A. All services"
    Write-Host "  Q. Quit"
    Write-Host ""
}

# Main
if ($All) {
    $Service = "all"
}

if ($Service -eq "" -and -not $All) {
    Show-Menu
    $choice = Read-Host "Select service (or 'A' for all)"
    if ($choice -eq "Q") { exit }
    if ($choice -eq "A") { $Service = "all" }
    else {
        $keys = ($Services.Keys | Sort-Object)
        $idx = [int]$choice - 1
        if ($idx -ge 0 -and $idx -lt $keys.Count) {
            $Service = $keys[$idx]
        }
    }
}

if ($Service -eq "all") {
    Write-Host "`n=== Starting all tunnels ===" -ForegroundColor Yellow
    $pids = @()
    foreach ($svcName in $Services.Keys) {
        $info = $Services[$svcName]
        $pid = Start-SSHTunnel -HostIP $VM_IPS[$info.Host] -LocalPort $info.LocalPort -RemotePort $info.RemotePort -ServiceName $svcName
        if ($pid) { $pids += $pid }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "`n=== All tunnels active ===" -ForegroundColor Green
    Write-Host "Access URLs:"
    Write-Host "  Grafana:     http://localhost:3000"
    Write-Host "  Prometheus:  http://localhost:9090"
    Write-Host "  AlertManager: http://localhost:9093"
    Write-Host "  Pushgateway: http://localhost:9091"
    Write-Host "  cAdvisor:    http://localhost:8080"
    Write-Host "  Target App:  http://localhost:80"
    Write-Host ""
    Write-Host "Press Ctrl+C to stop all tunnels" -ForegroundColor Yellow
} else {
    $info = $Services[$Service]
    if ($info) {
        Write-Host "=== Starting $($info.Desc) tunnel ===" -ForegroundColor Yellow
        Start-SSHTunnel -HostIP $VM_IPS[$info.Host] -LocalPort $info.LocalPort -RemotePort $info.RemotePort -ServiceName $Service
        Write-Host "`nAccess at: http://localhost:$($info.LocalPort)" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Unknown service: $Service" -ForegroundColor Red
    }
}
