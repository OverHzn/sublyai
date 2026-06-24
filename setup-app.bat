@echo off
title SublyAI Setup
cd /d "%~dp0"

set "REQ_FILE=requirements.txt"
if exist "resources\sublyai\requirements.txt" (
  set "REQ_FILE=resources\sublyai\requirements.txt"
)

echo.
echo  SublyAI - Setup Desktop App
echo  ============================
echo.

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [ERROR] ffmpeg tidak ada di PATH.
  if /I not "%~1"=="--no-pause" pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Membuat Python venv...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Gagal buat venv. Pastikan Python 3.10+ terinstall.
    if /I not "%~1"=="--no-pause" pause
    exit /b 1
  )
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\pip.exe install -r "%REQ_FILE%"
  if errorlevel 1 (
    echo [ERROR] pip install gagal.
    if /I not "%~1"=="--no-pause" pause
    exit /b 1
  )
)

if not exist "desktop\node_modules\electron" (
  echo [2/3] Install Electron...
  cd desktop
  npm install
  cd ..
)

echo [3/3] Setup selesai!
echo.
echo Jalankan app: double-click start-app.bat
echo Build installer: cd desktop ^&^& npm run build:win
echo.
if /I not "%~1"=="--no-pause" pause