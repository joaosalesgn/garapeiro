@echo off
setlocal
cd /d "%~dp0.."

echo Aplicando migracoes do banco...
.venv\Scripts\python.exe manage.py migrate

if errorlevel 1 (
    echo.
    echo Ocorreu um erro ao aplicar as migracoes.
    pause
    exit /b 1
)

echo.
echo Migracoes aplicadas com sucesso.
pause