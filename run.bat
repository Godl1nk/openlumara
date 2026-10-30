@echo off
setlocal enabledelayedexpansion

:: Switch to the directory where this .bat file is located
cd /d "%~dp0"

:: shared helpers: the environment lives in .venv\ for both uv and the pip
:: fallback, and venv\ is the legacy name from before uv was supported

:: a venv\ from before uv was supported is left alone; the environment
:: below is built from scratch in .venv\
call tools\venv.bat :note_legacy_venv

:: uv manages the environment when available, plain venv + pip otherwise
call tools\venv.bat :have_uv
if not errorlevel 1 goto :uv

echo uv not found, using venv + pip...
call tools\venv.bat :ensure_venv
if errorlevel 1 exit /b 1

echo starting openlumara...
.venv\Scripts\python main.py %*
goto :check

:uv
call tools\venv.bat :uv_sync
if errorlevel 1 exit /b 1
echo starting openlumara...
uv run --frozen --no-sync main.py %*

:check
if !errorlevel! neq 0 (
    echo.
    echo an error occurred while running the application.
    pause
)
