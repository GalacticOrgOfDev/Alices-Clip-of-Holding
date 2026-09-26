<#
.SYNOPSIS
    Build AlicesClipOfHolding.exe with PyInstaller (run on Windows).
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) { throw "Python is required to build the exe." }

& $python.Source -m pip install --upgrade pip
& $python.Source -m pip install -e $Root
& $python.Source -m pip install pyinstaller
& $python.Source -m PyInstaller --noconfirm --clean --workpath (Join-Path $Root "build") --distpath (Join-Path $Root "dist") (Join-Path $Root "packaging\AlicesClipOfHolding.spec")

$built = Join-Path $Root "dist\AlicesClipOfHolding.exe"
if (-not (Test-Path $built)) { throw "PyInstaller did not produce $built" }
Write-Host "Built $built"
Write-Host "Install with: .\dist\AlicesClipOfHolding.exe"
