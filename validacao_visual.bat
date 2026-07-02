@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if not exist logs mkdir logs >nul 2>nul
for /f %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format yyyyMMdd_HHmmss" 2^>nul') do set TS=%%I
if not defined TS set TS=sem_data_%RANDOM%
set VISUAL_LOG=%CD%\logs\validacao_visual_%TS%.log
set CHECKLIST=%CD%\CHECKLIST_VALIDACAO_VISUAL.md
set OUT_JSON=%CD%\logs\validacao_visual_%TS%.json

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

echo ===============================================
echo RecuperaAI - Validacao visual guiada
echo ===============================================
echo Pasta: %CD%
echo Comando diagnostico: %HEADLESS_CMD%
echo Comando interface: %GUI_CMD%
echo Checklist: %CHECKLIST%
echo Log: %VISUAL_LOG%
echo.

(
  echo ===============================================
  echo RecuperaAI - Validacao visual guiada
  echo Data/Hora: %date% %time%
  echo Pasta: %CD%
  echo Fonte detectada: %SOURCE_MODE%
  echo Comando diagnostico: %HEADLESS_CMD%
  echo Comando interface: %GUI_CMD%
  echo ===============================================
  echo.
  echo [1/3] Preparando massa de validacao e checklist
  %HEADLESS_CMD% --portable --visual-check --log-level DEBUG --output-file "%OUT_JSON%" --checklist-output "%CHECKLIST%"
  set PREP_CODE=!ERRORLEVEL!
  echo Codigo preparacao: !PREP_CODE!
  if exist "%OUT_JSON%" type "%OUT_JSON%"
  echo.
  echo [2/3] Checklist
  if exist "%CHECKLIST%" type "%CHECKLIST%"
  echo.
  echo [3/3] Abrindo interface
  echo Comando: %GUI_CMD% --portable
  %GUI_CMD% --portable
) > "%VISUAL_LOG%" 2>&1

set EXIT_CODE=%ERRORLEVEL%
type "%VISUAL_LOG%"
echo.
echo Validacao visual encerrada com codigo: %EXIT_CODE%
echo Checklist: %CHECKLIST%
echo Log: %VISUAL_LOG%
echo.
echo Pressione qualquer tecla para fechar...
pause >nul
exit /b %EXIT_CODE%
