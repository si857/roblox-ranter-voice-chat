@echo off
REM Double-click this file to start the Roblox Ranter Voice Chat on Windows.
REM The window ALWAYS stays open (it relaunches itself with cmd /k), so any
REM error stays on screen and you can read it.

if "%~1"=="" goto relaunch
goto main

:relaunch
cmd /k ""%~f0" go"
exit /b

:main
cd /d "%~dp0"
title Roblox Ranter Voice Chat

echo Folder: %cd%
echo.

if exist "app.py" goto have_app
echo ERROR: app.py was not found in this folder.
echo Put run_app.bat in the SAME folder as app.py.
echo If you opened it from inside a zip file, right-click the zip
echo and choose Extract All first.
goto end

:have_app
set PY=python
python --version >nul 2>&1
if not errorlevel 1 goto have_python
set PY=py
py --version >nul 2>&1
if not errorlevel 1 goto have_python
echo ERROR: Python was not found.
echo Install it from https://www.python.org/downloads/ and tick
echo "Add Python to PATH" in the installer, then run this again.
goto end

:have_python
echo Using: %PY%
%PY% --version
echo.
echo Installing / checking packages (the first time can take a few minutes)...
%PY% -m pip install streamlit openai requests pydub python-dotenv
echo.
echo Starting the app. Your browser should open at http://localhost:8501
echo Leave this window open while you use the app.
echo.
%PY% -m streamlit run app.py

:end
echo.
echo ----- Finished or stopped. Read any message above. -----
