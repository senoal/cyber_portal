#Requires -RunAsAdministrator
<#
Installs the Microsoft ODBC Driver 18 (x64) required by SEC_APP to connect
securely to SQL Server, then verifies that Python can see the driver.

Run this script from an elevated PowerShell window:
  powershell -ExecutionPolicy Bypass -File .\scripts\repair_sql_odbc.ps1
##>

$ErrorActionPreference = 'Stop'
$installerPath = Join-Path $env:TEMP 'msodbcsql18.msi'
$installerUrl = 'https://download.microsoft.com/download/7bf9fad4-0f21-486d-a750-fc990ded5624/amd64/1033/msodbcsql.msi'

Write-Host 'Downloading Microsoft ODBC Driver 18 for SQL Server...'
Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath

Write-Host 'Installing Microsoft ODBC Driver 18 for SQL Server...'
$process = Start-Process -FilePath 'msiexec.exe' -ArgumentList @(
    '/i', $installerPath, '/qn', 'IACCEPTMSODBCSQLLICENSETERMS=YES'
) -Wait -PassThru

if ($process.ExitCode -ne 0) {
    throw "ODBC installation failed with exit code $($process.ExitCode)."
}

$driverKey = 'HKLM:\SOFTWARE\ODBC\ODBCINST.INI\ODBC Driver 18 for SQL Server'
if (-not (Test-Path -LiteralPath $driverKey)) {
    throw 'ODBC Driver 18 was not registered after installation.'
}

Write-Host 'ODBC Driver 18 installed successfully. Restart run.py, then open VA Dashboard.' -ForegroundColor Green
