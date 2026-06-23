@echo off
title SublyAI Build
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Jalankan setup-app.bat dulu.
  pause
  exit /b 1
)

if not exist "desktop\node_modules\electron-builder" (
  echo Install dependencies desktop...
  cd desktop
  call npm install
  cd ..
)

echo Building SublyAI installer...
cd desktop
call npm run build:win
cd ..

echo.
echo [BONUS] Packaging portable lengkap ^(.venv included^)...
cd ..
call package-portable.bat

echo.
echo === HASIL BUILD ===
echo Installer:  desktop\dist\SublyAI Setup 1.0.0.exe
echo Portable:   desktop\dist\SublyAI 1.0.0.exe
echo Siap pakai: release\SublyAI-Portable\SublyAI.exe
echo.
echo Catatan: Installer NSIS butuh setup .venv sekali di folder install.
echo           Paket release\SublyAI-Portable sudah lengkap, bisa dipindah/copy.
echo.
pause