<#
.SYNOPSIS
    Remove Alice's Clip of Holding from this user account.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$AppId = "AlicesClipOfHolding"
$AppTitle = "Alice's Clip of Holding"
$DataDir = Join-Path $env:LOCALAPPDATA $AppId

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*alices_clip*" } |
    ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch { }
    }

$startup = Join-Path ([Environment]::GetFolderPath("Startup")) "$AppTitle.lnk"
$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppTitle.lnk"
foreach ($link in @($startup, $desktop)) {
    if (Test-Path $link) { Remove-Item $link -Force }
}

if (Test-Path $DataDir) {
    $answer = Read-Host "Delete saved clips in $DataDir as well? (y/N)"
    if ($answer -match "^[Yy]") {
        Remove-Item $DataDir -Recurse -Force
    } else {
        $venv = Join-Path $DataDir "venv"
        if (Test-Path $venv) { Remove-Item $venv -Recurse -Force }
        $launcher = Join-Path $DataDir "start.cmd"
        if (Test-Path $launcher) { Remove-Item $launcher -Force }
    }
}

Write-Host "Uninstalled $AppTitle."
