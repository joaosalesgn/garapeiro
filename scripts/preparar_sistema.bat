@echo off
setlocal
cd /d "%~dp0.."

echo Pasta do projeto: %CD%
echo.

if not exist "requirements.txt" (
    echo ERRO: nao encontrei requirements.txt nesta pasta.
    goto erro
)
if not exist "manage.py" (
    echo ERRO: nao encontrei manage.py nesta pasta.
    goto erro
)

echo [1/5] Verificando Python...
py -3 --version
if errorlevel 1 goto erro

echo.
echo [2/5] Criando ambiente virtual...
py -3 -m venv .venv
if errorlevel 1 goto erro

echo.
echo [3/5] Instalando dependencias...
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto erro
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto erro

echo.
echo [4/5] Preparando o banco de dados...
.venv\Scripts\python.exe manage.py migrate
if errorlevel 1 goto erro

echo.
echo [5/5] Criando usuario administrador...
.venv\Scripts\python.exe manage.py createsuperuser
if errorlevel 1 goto erro

echo.
echo Preparacao concluida. Use scripts\iniciar_sistema.bat para abrir o sistema.
pause
exit /b 0

:erro
echo.
echo A preparacao nao foi concluida. Leia a mensagem de erro exibida acima.
pause
exit /b 1