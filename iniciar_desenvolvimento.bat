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
python -m recuperaai
pause
