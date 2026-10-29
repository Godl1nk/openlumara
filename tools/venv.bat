@echo off
rem Shared helpers for run.bat and update.bat.
rem
rem The python environment lives in .venv\ for both uv and the plain pip
rem fallback, so an environment built by either one stays usable when the
rem other tool shows up later.
rem
rem venv\ is the legacy name from before uv was supported. migrate_venv
rem copies it to .venv\ so the packages that are already installed are
rem kept instead of being downloaded again. The old directory is left in
rem place as a fallback.
rem
rem usage: call tools\venv.bat :label
rem
rem   :have_uv      - succeeds when uv is on the PATH
rem   :uv_sync      - syncs the environment with uv
rem   :migrate_venv - copies a legacy venv\ to .venv\
rem   :create_venv  - creates .venv\ when it is missing
rem   :install_deps - installs the pinned requirements into .venv\
rem   :ensure_venv  - makes sure .venv\ exists and holds the requirements
rem   :refresh_venv - like :ensure_venv, but always reinstalls them

if "%~1"=="" goto :eof
goto %~1

:have_uv
where uv >nul 2>nul
if errorlevel 1 exit /b 1
exit /b 0

:uv_sync
rem --inexact keeps module dependencies the app installed at runtime
uv sync --frozen --inexact --extra webui --extra channels --extra modules
exit /b %errorlevel%

:migrate_venv
if not exist "venv" exit /b 0
if exist ".venv" exit /b 0
echo migrating venv\ to .venv\...
rem the console scripts in the copy still point at the old venv\, which
rem stays in place as a fallback
xcopy /E /I /Q /Y "venv" ".venv" >nul || exit /b 1
exit /b 0

:create_venv
if exist ".venv\Scripts\python.exe" exit /b 0
where python >nul 2>nul
if errorlevel 1 (
    echo error: no python binary found. please make sure python is installed and in your PATH.
    pause
    exit /b 1
)
echo setting up virtual environment...
python -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python -m pip install -q --upgrade pip
if errorlevel 1 exit /b 1
exit /b 0

:install_deps
.venv\Scripts\python tools\dump_requirements.py --groups webui,channels,modules --output .venv\requirements.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python -m pip install -r .venv\requirements.txt
if errorlevel 1 exit /b 1
exit /b 0

:ensure_venv
call "%~dp0venv.bat" :migrate_venv
if errorlevel 1 exit /b 1
if exist ".venv\Scripts\python.exe" exit /b 0
call "%~dp0venv.bat" :create_venv
if errorlevel 1 exit /b 1
call "%~dp0venv.bat" :install_deps
if errorlevel 1 exit /b 1
exit /b 0

:refresh_venv
call "%~dp0venv.bat" :migrate_venv
if errorlevel 1 exit /b 1
call "%~dp0venv.bat" :create_venv
if errorlevel 1 exit /b 1
call "%~dp0venv.bat" :install_deps
if errorlevel 1 exit /b 1
exit /b 0
