# SublyAI - jalankan lokal di Windows
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host " SublyAI - Local App" -ForegroundColor Cyan
Write-Host " ===================" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] ffmpeg tidak ada di PATH." -ForegroundColor Red
    exit 1
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "[1/2] Membuat virtual environment..."
    python -m venv .venv
    Write-Host "[2/2] Install dependencies (bisa beberapa menit)..."
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    & .\.venv\Scripts\pip.exe install -r requirements.txt
    Write-Host "Setup selesai!" -ForegroundColor Green
    Write-Host ""
}

Write-Host "Menjalankan SublyAI di http://127.0.0.1:8000"
Write-Host "Tekan Ctrl+C untuk stop."
Write-Host ""

& $python run_local.py