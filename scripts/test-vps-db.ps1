# Teste la connexion Django -> PostgreSQL VPS (connexion directe)
# Usage : .\scripts\test-vps-db.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "Test connexion PostgreSQL VPS (via .env)..." -ForegroundColor Cyan

& ".\venv\Scripts\python.exe" manage.py check --database default 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Echec: verifiez .env (DB_HOST, DB_PORT) et autorisation IP sur le VPS." -ForegroundColor Red
    Write-Host "Sur le VPS: sudo bash deploy/configure-postgres-remote.sh all" -ForegroundColor Yellow
    exit 1
}

& ".\venv\Scripts\python.exe" ".\scripts\test_vps_db.py"
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Connexion VPS OK - lancez runserver + Celery worker." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Echec connexion - configurez le VPS (deploy/configure-postgres-remote.sh)." -ForegroundColor Red
    exit 1
}
