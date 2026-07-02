@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if not exist logs mkdir logs >nul 2>nul
for /f %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format yyyyMMdd_HHmmss" 2^>nul') do set TS=%%I
if not defined TS set TS=sem_data_%RANDOM%
set RUN_LOG=%CD%\logs\execucao_recuperaai_%TS%.log

set SOURCE_MODE=0
if exist "%CD%\recuperaai\app.py" set SOURCE_MODE=1

set HEADLESS_CMD=
set GUI_CMD=
if "%SOURCE_MODE%"=="1" if exist "%CD%\.venv\Scripts\python.exe" set HEADLESS_CMD="%CD%\.venv\Scripts\python.exe" -m recuperaai
if "%SOURCE_MODE%"=="1" if not defined HEADLESS_CMD set HEADLESS_CMD=python -m recuperaai
if "%SOURCE_MODE%"=="1" set GUI_CMD=!HEADLESS_CMD!

if not defined HEADLESS_CMD if exist "%CD%\RecuperaAI\RecuperaAI_CLI.exe" set HEADLESS_CMD="%CD%\RecuperaAI\RecuperaAI_CLI.exe"
if not defined HEADLESS_CMD if exist "%CD%\dist\RecuperaAI\RecuperaAI_CLI.exe" set HEADLESS_CMD="%CD%\dist\RecuperaAI\RecuperaAI_CLI.exe"
if not defined HEADLESS_CMD if exist "%CD%\.venv\Scripts\python.exe" set HEADLESS_CMD="%CD%\.venv\Scripts\python.exe" -m recuperaai
if not defined HEADLESS_CMD set HEADLESS_CMD=python -m recuperaai

if not defined GUI_CMD if exist "%CD%\RecuperaAI\RecuperaAI.exe" set GUI_CMD="%CD%\RecuperaAI\RecuperaAI.exe"
if not defined GUI_CMD if exist "%CD%\dist\RecuperaAI\RecuperaAI.exe" set GUI_CMD="%CD%\dist\RecuperaAI\RecuperaAI.exe"
if not defined GUI_CMD set GUI_CMD=!HEADLESS_CMD!

set VERSION_TMP=%TEMP%\recuperaai_version_%RANDOM%.txt
set APP_VERSION_TEXT=nao_identificada
%HEADLESS_CMD% --version --output-file "%VERSION_TMP%" >nul 2>&1
set VERSION_CODE=%ERRORLEVEL%
for /f "usebackq delims=" %%L in ("%VERSION_TMP%") do if "!APP_VERSION_TEXT!"=="nao_identificada" set APP_VERSION_TEXT=%%L
if exist "%VERSION_TMP%" del "%VERSION_TMP%" >nul 2>nul

set SUPPORTS_LOG_ARGS=0
echo !APP_VERSION_TEXT! | findstr /i /c:"etapa" >nul 2>nul
if not errorlevel 1 set SUPPORTS_LOG_ARGS=1
set EXTRA_LOG_ARGS=
if "%SUPPORTS_LOG_ARGS%"=="1" set EXTRA_LOG_ARGS=--log-level DEBUG --log-console

echo ===============================================
echo RecuperaAI - Execucao com diagnostico
echo ===============================================
echo Pasta: %CD%
echo Fonte detectada: %SOURCE_MODE%
echo Comando diagnostico: %HEADLESS_CMD%
echo Comando interface: %GUI_CMD%
echo Versao detectada: !APP_VERSION_TEXT!
echo Log desta execucao: %RUN_LOG%
echo Dica: se a versao estiver errada, execute limpar_build_antigo.bat e depois build_windows.bat.
echo Observacao: codigo 2 geralmente indica executavel antigo recusando argumentos.
echo.
echo O aplicativo tambem grava o log interno em:
echo - modo normal Windows: %%LOCALAPPDATA%%\RecuperaAI\logs\recuperaai_app.log
echo - modo portable: pasta dados\logs ao lado do executavel
echo.
echo Iniciando...
echo.

(
  echo ===============================================
  echo RecuperaAI - Execucao com diagnostico
  echo Data/Hora: %date% %time%
  echo Pasta: %CD%
  echo Fonte detectada: %SOURCE_MODE%
  echo Comando diagnostico: %HEADLESS_CMD%
  echo Comando interface: %GUI_CMD%
  echo Versao detectada: !APP_VERSION_TEXT!
  echo Codigo versao: %VERSION_CODE%
  echo ===============================================
  echo.
  echo [Ambiente]
  echo PATH=%PATH%
  echo.
  echo [Python encontrado]
  where python
  echo.
  echo [Diagnostico antes da interface]
  set DIAG_TMP=%TEMP%\recuperaai_diag_%RANDOM%.json
  %HEADLESS_CMD% --portable --diagnostics %EXTRA_LOG_ARGS% --output-file "!DIAG_TMP!"
  set DIAG_CODE=!ERRORLEVEL!
  if exist "!DIAG_TMP!" type "!DIAG_TMP!"
  if exist "!DIAG_TMP!" del "!DIAG_TMP!" >nul 2>nul
  echo Codigo diagnostico: !DIAG_CODE!
  echo.
  echo [Abrindo aplicativo]
  echo Comando completo: %GUI_CMD% --portable %EXTRA_LOG_ARGS% %*
  %GUI_CMD% --portable %EXTRA_LOG_ARGS% %*
) >> "%RUN_LOG%" 2>&1

set EXIT_CODE=%ERRORLEVEL%
echo.
echo Aplicativo encerrado com codigo: %EXIT_CODE%
echo Log da execucao: %RUN_LOG%
echo.
echo Se alguma funcionalidade falhou, envie tambem o arquivo:
echo dados\logs\recuperaai_app.log
echo.
echo Pressione qualquer tecla para fechar...
pause >nul
exit /b %EXIT_CODE%
