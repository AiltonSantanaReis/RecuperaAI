@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist logs mkdir logs >nul 2>nul
for /f "tokens=1-4 delims=/ " %%a in ("%date%") do set _date=%%d%%b%%c
for /f "tokens=1-3 delims=:,. " %%a in ("%time%") do set _time=%%a%%b%%c
set _time=%_time: =0%
set BUILD_LOG=%CD%\logs\build_windows_%_date%_%_time%.log

echo ===============================================
echo RecuperaAI - Build Windows / Cliente Teste
echo ===============================================
echo Pasta do projeto: %CD%
echo Log do build: %BUILD_LOG%
echo.

where powershell >nul 2>nul
if errorlevel 1 (
  echo ERRO: PowerShell nao encontrado.
  echo ERRO: PowerShell nao encontrado. > "%BUILD_LOG%"
  goto :fail
)

echo Executando build. A saida completa sera salva no log.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_windows.ps1" %* > "%BUILD_LOG%" 2>&1
set EXIT_CODE=%ERRORLEVEL%

type "%BUILD_LOG%"

if not "%EXIT_CODE%"=="0" goto :fail

echo.
echo ===============================================
echo Build concluido com sucesso.
echo Log salvo em: %BUILD_LOG%
echo ===============================================
goto :end

:fail
echo.
echo ===============================================
echo BUILD FALHOU.
echo Codigo de erro: %EXIT_CODE%
echo Log salvo em: %BUILD_LOG%
echo.
echo Envie o arquivo de log para analise.
echo ===============================================
if "%EXIT_CODE%"=="0" set EXIT_CODE=1

:end
echo.
echo Pressione qualquer tecla para fechar...
pause >nul
exit /b %EXIT_CODE%
