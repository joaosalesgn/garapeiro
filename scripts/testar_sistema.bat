@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente do sistema nao foi configurado. Consulte README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" manage.py check
if errorlevel 1 goto erro
".venv\Scripts\python.exe" manage.py test atendimento
if errorlevel 1 goto erro
echo.
echo Verificacoes concluidas com sucesso.
pause
exit /b 0
:erro
echo.
echo Uma verificacao falhou. Confira a mensagem acima.
pause
exit /b 1
