@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
if "%MOSSVIEW_OUTPUT_NAME%"=="" set "MOSSVIEW_OUTPUT_NAME=MossView-windows"

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "%MOSSVIEW_OUTPUT_NAME%" ^
  --icon "%SCRIPT_DIR%assets\icon\mossview-logo.ico" ^
  --add-data "%SCRIPT_DIR%assets;assets" ^
  "%SCRIPT_DIR%gui.py"

if errorlevel 1 exit /b %errorlevel%