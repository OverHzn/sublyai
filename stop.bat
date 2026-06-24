@echo off
title Stop SublyAI
echo Mencari proses SublyAI...

powershell -NoProfile -Command ^
  "$ports = 8000..8009; " ^
  "Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | " ^
  "Where-Object { $ports -contains $_.LocalPort } | " ^
  "ForEach-Object { Write-Host ('Stop PID ' + $_.OwningProcess + ' pada port ' + $_.LocalPort); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; " ^
  "Get-CimInstance Win32_Process | " ^
  "Where-Object { $_.CommandLine -match 'run_server\.py|uvicorn app:app' } | " ^
  "ForEach-Object { Write-Host ('Stop Python PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo Selesai. Port dibersihkan.
pause