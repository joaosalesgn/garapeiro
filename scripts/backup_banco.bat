@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente nao encontrado. Consulte README.md.
  pause
  exit /b 1
)
.venv\Scripts\python.exe manage.py backup_sqlite
if errorlevel 1 (
  echo Falha ao criar backup. Confira as mensagens acima.
  pause
  exit /b 1
)
echo Backup concluido.
pause
