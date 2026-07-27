# Teste la connexion Django → PostgreSQL VPS (connexion directe)
# Usage : .\scripts\test-vps-db.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "Test connexion PostgreSQL VPS (via .env)..." -ForegroundColor Cyan

& ".\venv\Scripts\python.exe" manage.py check --database default 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Echec — verifiez .env (DB_HOST, DB_PORT) et l'autorisation IP sur le VPS." -ForegroundColor Red
    Write-Host "Sur le VPS : sudo bash deploy/configure-postgres-remote.sh VOTRE_IP" -ForegroundColor Yellow
    exit 1
}

& ".\venv\Scripts\python.exe" -c @"
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yayematy_project.settings')
django.setup()
from django.db import connection
with connection.cursor() as c:
    c.execute('SELECT current_database(), current_user')
    db, user = c.fetchone()
print(f'OK — base={db}, user={user}')
"@

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Connexion VPS OK — lancez runserver + Celery worker." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Echec connexion — configurez le VPS (deploy/configure-postgres-remote.sh)." -ForegroundColor Red
    exit 1
}
