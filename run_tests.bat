@echo off
setlocal
cd /d "%~dp0"
if not exist .venv (
  py -3.11 -m venv .venv
  if errorlevel 1 py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if exist requirements-lock.txt (
  pip install -r requirements-lock.txt
) else (
  pip install -r requirements.txt
)
python -m compileall -q recuperaai tests
if errorlevel 1 exit /b %ERRORLEVEL%
python -W error::ResourceWarning -m unittest discover -s tests -v
if errorlevel 1 exit /b %ERRORLEVEL%
set SMOKE_DIR=%TEMP%\RecuperaAI_Source_Smoke_%RANDOM%%RANDOM%
python -m recuperaai --smoke-test --base-dir "%SMOKE_DIR%"
set SMOKE_CODE=%ERRORLEVEL%
rmdir /s /q "%SMOKE_DIR%" >nul 2>nul
exit /b %SMOKE_CODE%
