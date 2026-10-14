# Local run on this computer only (no auth yet — never expose it on a network).
# Usage from the repository root:  powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
param(
    [string]$Python = "py -3.12",
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv with $Python ..."
    Invoke-Expression "$Python -m venv .venv"
}
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.lock

$env:DATABASE_URL = "sqlite:///./data/local.db"
.\.venv\Scripts\python.exe -m alembic upgrade head

Write-Host "Open http://127.0.0.1:$Port/ (Ctrl+C to stop)"
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $Port
