@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ===============================================
echo RecuperaAI - Limpeza de build antigo
echo ===============================================
echo Pasta: %CD%
echo.

echo Esta rotina remove arquivos gerados anteriormente para evitar usar EXE antigo.
echo Ela NAO apaga seus dados em dados\, nem o banco SQLite.
echo.

if exist dist (
  echo Removendo dist\ ...
  rmdir /s /q dist
)
if exist build (
  echo Removendo build\ ...
  rmdir /s /q build
)
if exist release (
  echo Removendo release\ ...
  rmdir /s /q release
)
if exist RecuperaAI (
  echo Removendo pasta RecuperaAI\ de pacote antigo ...
  rmdir /s /q RecuperaAI
)

echo.
echo Limpeza concluida.
echo Agora rode: build_windows.bat
echo.
pause
exit /b 0
