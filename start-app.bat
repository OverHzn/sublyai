@echo off
title SublyAI Desktop
cd /d "%~dp0"

echo.
echo  SublyAI Desktop App
echo  ===================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [SETUP] Virtual environment belum ada. Menjalankan setup...
  call "%~dp0start.bat"
  if not exist ".venv\Scripts\python.exe" exit /b 1
)

if not exist "desktop\node_modules\electron" (
  echo [SETUP] Install Electron shell...
  cd desktop
  call npm install
  cd ..
)

echo Membuka SublyAI sebagai desktop app...
cd desktop
call npm start
cd ..