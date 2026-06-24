@echo off
title SublyAI - Package Portable
cd /d "%~dp0"

set "OUT=%~dp0release\SublyAI-Portable"
set "SRC=%~dp0desktop\dist\win-unpacked"

echo.
echo  Packaging SublyAI Portable (app + Python venv)
echo  ==============================================
echo.

if not exist "%SRC%\SublyAI.exe" (
  echo [ERROR] Build belum ada. Jalankan build-app.bat dulu.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv belum ada. Jalankan setup-app.bat dulu.
  pause
  exit /b 1
)

echo [1/3] Copy app files...
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%"
xcopy "%SRC%\*" "%OUT%\" /E /I /H /Y /Q >nul

echo [2/3] Copy Python venv ^(bisa beberapa menit^)...
xcopy ".venv" "%OUT%\.venv\" /E /I /H /Y /Q >nul

echo [3/3] Tulis catatan data app...
(
echo Data job ^(downloads, outputs, jobs, config^) disimpan di:
echo   %%LOCALAPPDATA%%\SublyAI
echo Bukan di folder portable ini.
) > "%OUT%\DATA-LOCATION.txt"

(
echo @echo off
echo cd /d "%%~dp0"
echo start "" "%%~dp0SublyAI.exe"
) > "%OUT%\Jalankan SublyAI.bat"

echo.
echo Selesai!
echo Folder: %OUT%
echo Jalankan: "%OUT%\SublyAI.exe"
echo.
pause