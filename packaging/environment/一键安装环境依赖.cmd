@echo off
setlocal
PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-123MSHubEnvironment.ps1"
if errorlevel 1 (
  echo.
  echo 环境安装未完成，请查看上面的错误信息。
  pause
  exit /b 1
)
echo.
echo 环境检查/安装已完成。
pause
