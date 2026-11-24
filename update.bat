@echo off
setlocal

:: Switch to the directory where this .bat file is located
cd /d "%~dp0"

:: -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-25 07:33 +08:00 harness:Codex
git remote get-url origin >nul 2>nul
if errorlevel 1 git remote add origin https://github.com/Godl1nk/openlumara.git >nul 2>nul

:: 1. Smart auto-update
echo checking for updates...
git pull --ff-only
if errorlevel 1 exit /b 1

:: 2. Ensure dependencies are up to date
echo ensuring dependencies are up to date...
call tools\venv.bat :have_uv
if errorlevel 1 goto :pip

call tools\venv.bat :uv_sync
if errorlevel 1 exit /b 1
goto :done

:: the requirements are reinstalled, so a changed requirements.txt is
:: picked up even when the environment already existed
:pip
echo uv not found, using venv + pip...
call tools\venv.bat :refresh_venv
if errorlevel 1 exit /b 1

:done
echo.
echo done!
