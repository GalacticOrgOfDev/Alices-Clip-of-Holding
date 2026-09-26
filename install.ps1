<#
.SYNOPSIS
    Install Alice's Clip of Holding for this user.

.DESCRIPTION
    Prefers a shipped AlicesClipOfHolding.exe (no Python needed).
    Falls back to a per-user virtualenv when only source is present.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$AppId = "AlicesClipOfHolding"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataDir = Join-Path $env:LOCALAPPDATA $AppId
$BinDir = Join-Path $DataDir "bin"
$LogFile = Join-Path $DataDir "install.log"

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
Start-Transcript -Path $LogFile -Append | Out-Null

try {
    $shipped = @(
        (Join-Path $Root "AlicesClipOfHolding.exe"),
        (Join-Path $Root "dist\AlicesClipOfHolding.exe")
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ($shipped) {
        New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
        $dest = Join-Path $BinDir "AlicesClipOfHolding.exe"
        Copy-Item $shipped $dest -Force
        Write-Host "Installing $dest"
        Start-Process -FilePath $dest -ArgumentList "--install" -Wait
        Start-Process -FilePath $dest
    } else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
        if (-not $python) {
            throw "No AlicesClipOfHolding.exe found and Python is not on PATH. Download the exe from GitHub Releases, or install Python 3.10+ and re-run."
        }
        $venvDir = Join-Path $DataDir "venv"
        Write-Host "Creating virtual environment at $venvDir"
        & $python.Source -m venv $venvDir
        $venvPy = Join-Path $venvDir "Scripts\python.exe"
        & $venvPy -m pip install --upgrade pip
        & $venvPy -m pip install -r (Join-Path $Root "requirements.txt")
        & $venvPy -m pip install -e $Root
        & $venvPy -m alices_clip --install
        Start-Process -FilePath $venvPy -ArgumentList "-m alices_clip" -WorkingDirectory $DataDir -WindowStyle Hidden
    }

    Write-Host ""
    Write-Host "Installed."
    Write-Host "  Apps & Features : Uninstall from Settings > Apps"
    Write-Host "  Explorer        : right-click files / folder background"
    Write-Host "  Copy            : Ctrl+C or context Copy (also saved to the bag)"
    Write-Host "  Paste menu      : Ctrl+V"
    Write-Host "  Last item       : Ctrl+Shift+V"
}
finally {
    Stop-Transcript | Out-Null
}
