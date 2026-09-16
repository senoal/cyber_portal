[CmdletBinding()]
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

& (Join-Path $PSScriptRoot "test_production_ready.ps1") -Python $Python
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$hostAddress = if ($env:SEC_APP_HOST) { $env:SEC_APP_HOST } else { "0.0.0.0" }
$port = if ($env:SEC_APP_PORT) { $env:SEC_APP_PORT } else { "5000" }
& $Python -m waitress --host=$hostAddress --port=$port wsgi:app
