<#
.SYNOPSIS
    Install Alice's Clip of Holding so it starts with Windows and just works.

.DESCRIPTION
    Creates a per-user virtualenv under %LOCALAPPDATA%\AlicesClipOfHolding\venv,
    installs dependencies, writes a launcher, and drops a Startup shortcut.
    Run this from the unzipped repo or a git clone:

        powershell -ExecutionPolicy Bypass -File .\install.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$AppId = "AlicesClipOfHolding"
$AppTitle = "Alice's Clip of Holding"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataDir = Join-Path $env:LOCALAPPDATA $AppId
$VenvDir = Join-Path $DataDir "venv"
$Launcher = Join-Path $DataDir "start.cmd"
$LogFile = Join-Path $DataDir "install.log"

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
Start-Transcript -Path $LogFile -Append | Out-Null

try {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        $python = Get-Command py -ErrorAction SilentlyContinue
    }
    if (-not $python) {
        throw "Python 3.11+ was not found on PATH. Install it from https://www.python.org/downloads/windows/ and tick 'Add python.exe to PATH', then re-run install.ps1."
    }

    Write-Host "Using $($python.Source)"
    & $python.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.10 or newer is required."
    }

    Write-Host "Creating virtual environment at $VenvDir"
    & $python.Source -m venv $VenvDir
    $venvPy = Join-Path $VenvDir "Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        throw "venv python was not created at $venvPy"
    }

    Write-Host "Installing package"
    & $venvPy -m pip install --upgrade pip
    & $venvPy -m pip install -r (Join-Path $Root "requirements.txt")
    & $venvPy -m pip install -e $Root

    $startCmd = @"
@echo off
start "" "$venvPy" -m alices_clip
"@
    Set-Content -Path $Launcher -Value $startCmd -Encoding ASCII

    $startup = [Environment]::GetFolderPath("Startup")
    $shortcutPath = Join-Path $startup "$AppTitle.lnk"
    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $venvPy
    $shortcut.Arguments = "-m alices_clip"
    $shortcut.WorkingDirectory = $DataDir
    $shortcut.WindowStyle = 7
    $shortcut.Description = $AppTitle
    $shortcut.Save()

    $desktop = [Environment]::GetFolderPath("Desktop")
    $deskLink = Join-Path $desktop "$AppTitle.lnk"
    $desk = $wsh.CreateShortcut($deskLink)
    $desk.TargetPath = $venvPy
    $desk.Arguments = "-m alices_clip"
    $desk.WorkingDirectory = $DataDir
    $desk.Description = $AppTitle
    $desk.Save()

    Write-Host "Starting $AppTitle"
    Start-Process -FilePath $venvPy -ArgumentList "-m alices_clip" -WorkingDirectory $DataDir -WindowStyle Hidden

    Write-Host ""
    Write-Host "Installed."
    Write-Host "  Bag folder : $DataDir\clips"
    Write-Host "  Copy       : Ctrl+C or right-click Copy  (also saved to the bag)"
    Write-Host "  Paste menu : Ctrl+V"
    Write-Host "  Last item  : Ctrl+Shift+V"
    Write-Host "  Tray icon  : bag in the notification area"
    Write-Host "  Uninstall  : powershell -ExecutionPolicy Bypass -File .\uninstall.ps1"
}
finally {
    Stop-Transcript | Out-Null
}
