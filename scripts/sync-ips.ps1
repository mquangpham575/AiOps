<#
.SYNOPSIS
    Final Demo Insurance: Syncs all project documentation with current Azure Public IPs.
    Run this if your VMs provide new IPs upon startup.
#>

$OldControl = "104.215.158.157"
$OldLoadGen = "104.215.191.69"
$OldApp     = "4.194.57.3"

Write-Host "🔍 Fetching current Azure IP status..." -ForegroundColor Cyan
# Re-use status logic from aiops-power.ps1
$StatusOutput = .\scripts\aiops-power.ps1 status

# Parse New IPs (Assuming Standard Output Format)
$NewControl = ($StatusOutput | Select-String "CONTROL").ToString().Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)[2]
$NewLoadGen = ($StatusOutput | Select-String "LOADGEN").ToString().Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)[2]
$NewApp     = ($StatusOutput | Select-String "APP").ToString().Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)[2]

if (!$NewControl -or $NewControl -eq "OFFLINE") {
    Write-Error "❌ Error: Nodes appear to be OFFLINE. Please start them first."
    exit
}

Write-Host "🚀 Detected New IPs:" -ForegroundColor Green
Write-Host "   Control: $NewControl"
Write-Host "   LoadGen: $NewLoadGen"
Write-Host "   App:     $NewApp"

$FilesToSync = @("README.md", "agent-testing.md", "demo-guide.md")

foreach ($File in $FilesToSync) {
    if (Test-Path $File) {
        Write-Host "📝 Syncing $File..." -ForegroundColor Yellow
        (Get-Content $File) | 
            Foreach-Object { $_ -replace $OldControl, $NewControl } |
            Foreach-Object { $_ -replace $OldLoadGen, $NewLoadGen } |
            Foreach-Object { $_ -replace $OldApp, $NewApp } |
            Set-Content $File
    }
}

Write-Host "✅ Global Sync Complete. Your documentation and prompts are ready for the demo!" -ForegroundColor Green
