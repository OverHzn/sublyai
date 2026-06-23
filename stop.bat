@echo off
title Stop SublyAI
echo Mencari proses di port 8000-8009...

for /L %%p in (8000,1,8009) do (
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%p " ^| findstr LISTENING') do (
    echo Stop PID %%a pada port %%p
    taskkill /PID %%a /F >nul 2>&1
  )
)

echo Selesai. Port dibersihkan.
pause