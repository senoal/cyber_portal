[CmdletBinding()]
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# Allow a portable, gitignored production.env for offline development and
# copy-and-run deployments. Existing service environment values win.
$envFile = Join-Path $projectRoot "production.env"
if (Test-Path -LiteralPath $envFile) {
    foreach ($rawLine in Get-Content -LiteralPath $envFile) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { continue }
        $name, $value = $line.Split("=", 2)
        if ($name.Trim().StartsWith("SEC_APP_") -and -not [Environment]::GetEnvironmentVariable($name.Trim(), "Process")) {
            Set-Item -Path ("Env:" + $name.Trim()) -Value $value.Trim()
        }
    }
}

$required = @(
    "SEC_APP_DATABASE_ENGINE",
    "SEC_APP_DB_SERVER",
    "SEC_APP_DB_PORT",
    "SEC_APP_DB_DATABASE",
    "SEC_APP_DB_UID",
    "SEC_APP_DB_PASSWORD"
)

$missing = @($required | Where-Object { [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_, "Process")) })
if ($missing.Count -gt 0) {
    throw "Konfigurasi production belum lengkap: $($missing -join ', ')"
}
if ($env:SEC_APP_DATABASE_ENGINE.ToLowerInvariant() -ne "mssql") {
    throw "SEC_APP_DATABASE_ENGINE harus bernilai mssql untuk deployment production."
}

& $Python -c "import flask, waitress, pymssql, pandas, openpyxl, matplotlib, reportlab, fitz, pypdf, PIL, pytesseract, playwright"
if ($LASTEXITCODE -ne 0) {
    throw "Dependency belum lengkap. Jalankan: $Python -m pip install -r requirements.txt"
}

foreach ($directory in @("uploads", "static\uploads", "tmp", "instance")) {
    $path = Join-Path $projectRoot $directory
    New-Item -ItemType Directory -Path $path -Force | Out-Null
    $probe = Join-Path $path (".sec_app_write_probe_" + [guid]::NewGuid().ToString("N"))
    [System.IO.File]::WriteAllText($probe, "ok")
    Remove-Item -LiteralPath $probe -Force
}

& $Python -m app.database.test
if ($LASTEXITCODE -ne 0) { throw "Health check database gagal." }
& $Python -c "from wsgi import app; print('WSGI routes=' + str(len(list(app.url_map.iter_rules()))))"
if ($LASTEXITCODE -ne 0) { throw "WSGI application gagal dimuat." }

Write-Host "SEC_APP siap dijalankan dengan MSSQL." -ForegroundColor Green
