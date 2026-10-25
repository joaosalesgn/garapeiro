@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente do sistema nao foi configurado. Consulte README.md.
  pause
  exit /b 1
)

REM Se o servidor ja estiver ativo, nao inicia outra instancia.
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1',8000); exit 0 } catch { exit 1 } finally { $c.Dispose() }" >nul 2>&1
if not errorlevel 1 goto abrir_navegador

REM Inicia o Django em uma janela separada.
start "Servidor da pastelaria" /D "%CD%" "%CD%\.venv\Scripts\python.exe" manage.py runserver 0.0.0.0:8000

REM Aguarda ate 60 segundos para a porta do servidor responder.
set /a tentativas=0
:aguardar_servidor
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1',8000); exit 0 } catch { exit 1 } finally { $c.Dispose() }" >nul 2>&1
if not errorlevel 1 goto abrir_navegador
set /a tentativas+=1
if %tentativas% geq 60 goto erro_servidor
timeout /t 1 /nobreak >nul
goto aguardar_servidor

:abrir_navegador
start "" "http://localhost:8000/"
exit /b 0

:erro_servidor
echo O servidor nao respondeu em 60 segundos. Verifique a janela do servidor.
pause
exit /b 1
