@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente do sistema nao foi configurado. Consulte README.md.
  pause
  exit /b 1
)
@REM start "Sistema da pastelaria" "http://localhost:8000/admin/"
start "Sistema da pastelaria" "http://localhost:8000/"
".venv\Scripts\python.exe" manage.py runserver localhost:8000
