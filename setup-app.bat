@echo off
title SublyAI Setup
cd /d "%~dp0"

echo.
echo  SublyAI - Setup Desktop App
echo  ============================
echo.

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [ERROR] ffmpeg tidak ada di PATH.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Membuat Python venv...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\pip.exe install -r requirements.txt
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
pause