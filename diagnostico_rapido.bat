@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if not exist logs mkdir logs >nul 2>nul
for /f %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format yyyyMMdd_HHmmss" 2^>nul') do set TS=%%I
if not defined TS set TS=sem_data_%RANDOM%
set DIAG_LOG=%CD%\logs\diagnostico_recuperaai_%TS%.log

set SOURCE_MODE=0
if exist "%CD%\recuperaai\app.py" set SOURCE_MODE=1
set APP_CMD=
if "%SOURCE_MODE%"=="1" if exist "%CD%\.venv\Scripts\python.exe" set APP_CMD="%CD%\.venv\Scripts\python.exe" -m recuperaai
if "%SOURCE_MODE%"=="1" if not defined APP_CMD set APP_CMD=python -m recuperaai
if not defined APP_CMD if exist "%CD%\RecuperaAI\RecuperaAI_CLI.exe" set APP_CMD="%CD%\RecuperaAI\RecuperaAI_CLI.exe"
if not defined APP_CMD if exist "%CD%\dist\RecuperaAI\RecuperaAI_CLI.exe" set APP_CMD="%CD%\dist\RecuperaAI\RecuperaAI_CLI.exe"
if not defined APP_CMD if exist "%CD%\.venv\Scripts\python.exe" set APP_CMD="%CD%\.venv\Scripts\python.exe" -m recuperaai
if not defined APP_CMD set APP_CMD=python -m recuperaai

set VERSION_TMP=%TEMP%\recuperaai_version_%RANDOM%.txt
set APP_VERSION_TEXT=nao_identificada
%APP_CMD% --version --output-file "%VERSION_TMP%" >nul 2>&1
set VERSION_CODE=%ERRORLEVEL%
for /f "usebackq delims=" %%L in ("%VERSION_TMP%") do if "!APP_VERSION_TEXT!"=="nao_identificada" set APP_VERSION_TEXT=%%L
if exist "%VERSION_TMP%" del "%VERSION_TMP%" >nul 2>nul

set EXTRA_LOG_ARGS=--log-level DEBUG --log-console

echo ===============================================
echo RecuperaAI - Diagnostico rapido
echo ===============================================
echo Pasta: %CD%
echo Fonte detectada: %SOURCE_MODE%
echo Comando diagnostico: %APP_CMD%
echo Versao detectada: !APP_VERSION_TEXT!
echo Log: %DIAG_LOG%
echo.

(
  echo ===============================================
  echo RecuperaAI - Diagnostico rapido
  echo Data/Hora: %date% %time%
  echo Pasta: %CD%
  echo Fonte detectada: %SOURCE_MODE%
  echo Comando base: %APP_CMD%
  echo Versao detectada: !APP_VERSION_TEXT!
  echo Codigo versao: %VERSION_CODE%
  echo ===============================================
  echo.
  echo [0/5] Ambiente
  where python
  python --version
  echo.
  echo [1/5] Versao
  echo !APP_VERSION_TEXT!
  echo Codigo versao: %VERSION_CODE%
  echo.
  echo [2/5] Diagnostico
  set DIAG_TMP=%TEMP%\recuperaai_diag_%RANDOM%.json
  %APP_CMD% --portable --diagnostics %EXTRA_LOG_ARGS% --output-file "!DIAG_TMP!"
  set DIAG_CODE=!ERRORLEVEL!
  if exist "!DIAG_TMP!" type "!DIAG_TMP!"
  if exist "!DIAG_TMP!" del "!DIAG_TMP!" >nul 2>nul
  echo Codigo diagnostico: !DIAG_CODE!
  echo.
  echo [3/5] Smoke test
  set SMOKE_TMP=%TEMP%\recuperaai_smoke_%RANDOM%.json
  %APP_CMD% --portable --smoke-test --keep-smoke-data %EXTRA_LOG_ARGS% --output-file "!SMOKE_TMP!"
  set SMOKE_CODE=!ERRORLEVEL!
  if exist "!SMOKE_TMP!" type "!SMOKE_TMP!"
  if exist "!SMOKE_TMP!" del "!SMOKE_TMP!" >nul 2>nul
  echo Codigo smoke: !SMOKE_CODE!
  echo.
  echo [4/5] Arquivos de log internos
  if exist dados\logs\recuperaai_app.log type dados\logs\recuperaai_app.log
  echo.
  echo [5/5] Fim
) > "%DIAG_LOG%" 2>&1

set EXIT_CODE=%ERRORLEVEL%
type "%DIAG_LOG%"
echo.
echo Diagnostico encerrado com codigo: %EXIT_CODE%
echo Envie este arquivo se houver falha: %DIAG_LOG%
echo.
echo Pressione qualquer tecla para fechar...
pause >nul
exit /b %EXIT_CODE%
