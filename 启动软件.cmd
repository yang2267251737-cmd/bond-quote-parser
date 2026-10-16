@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" app.py
  goto end
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 app.py
  goto end
)
where python >nul 2>nul
if not errorlevel 1 (
  python app.py
  goto end
)
echo 请先安装 Python 3.10 或以上版本，再重新启动。
:end
if errorlevel 1 pause
