@echo off
title SublyAI Local
cd /d "%~dp0"

echo.
echo  SublyAI - Local App
echo  ===================
echo.

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [ERROR] ffmpeg tidak ada di PATH. Install dulu: https://ffmpeg.org
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/2] Membuat virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Gagal buat venv. Pastikan Python 3.10+ terinstall.
    pause
    exit /b 1
  )
  echo [2/2] Install dependencies ^(bisa beberapa menit^)...
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\pip.exe install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] pip install gagal.
    pause
    exit /b 1
  )
  echo.
  echo Setup selesai!
  echo.
)

echo Menjalankan SublyAI di http://127.0.0.1:8000
echo Browser akan terbuka otomatis. Tutup jendela ini untuk stop server.
echo.

.venv\Scripts\python.exe run_local.py

pause