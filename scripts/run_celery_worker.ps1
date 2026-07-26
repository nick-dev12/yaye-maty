# Worker Celery — Windows (pool solo obligatoire)
# Usage : .\scripts\run_celery_worker.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (Test-Path ".\venv\Scripts\Activate.ps1") {
    & ".\venv\Scripts\Activate.ps1"
}

Write-Host "Demarrage Celery worker (pool=solo)..." -ForegroundColor Cyan
Write-Host "Important : apres une modif Python, Ctrl+C puis relancez ce script." -ForegroundColor DarkGray
celery -A yayematy_project worker -l info -P solo --concurrency=1
