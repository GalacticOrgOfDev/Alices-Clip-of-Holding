<#
.SYNOPSIS
    Remove Alice's Clip of Holding. Asks whether to keep or delete clip files.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$AppId = "AlicesClipOfHolding"
$DataDir = Join-Path $env:LOCALAPPDATA $AppId
$Exe = Join-Path $DataDir "bin\AlicesClipOfHolding.exe"
$VenvPy = Join-Path $DataDir "venv\Scripts\python.exe"

if (Test-Path $Exe) {
    Start-Process -FilePath $Exe -ArgumentList "--uninstall" -Wait
} elseif (Test-Path $VenvPy) {
    & $VenvPy -m alices_clip --uninstall
} else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & $python.Source -m alices_clip --uninstall
    } else {
        throw "Alice's Clip of Holding does not appear to be installed."
    }
}
