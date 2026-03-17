@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo =======================================================
echo          WW1 ^& WW2 Agentic Trivia CLI Setup
echo =======================================================

:: OTA Update for the Offline Knowledge Bank
set "OTA_URL=https://raw.githubusercontent.com/adityasricharan/wwq/master/questions.enc"
if not "%OTA_URL%"=="" (
    curl -s --head -f "%OTA_URL%" >nul 2>&1
    if !errorlevel! equ 0 (
        :: Check if user has a custom bank active (questions.enc.official exists)
        if exist "questions.enc.official" (
            :: User has a custom bank — update official backup only, leave custom bank intact
            echo [INFO] Checking for official knowledge bank updates...
            curl -s -L -o "questions.enc.official.tmp" "%OTA_URL%"
            if exist "questions.enc.official.tmp" (
                move /y "questions.enc.official.tmp" "questions.enc.official" >nul
                echo [INFO] Official bank updated in background. Your custom bank is unchanged.
            )
        ) else (
            :: User is on official bank — update questions.enc directly
            echo [INFO] Checking for offline knowledge bank updates...
            curl -s -L -o "questions.enc.tmp" "%OTA_URL%"
            if exist "questions.enc.tmp" (
                move /y "questions.enc.tmp" "questions.enc" >nul
                echo [INFO] Knowledge bank updated successfully.
            )
        )
    )
)

:: Code OTA — check for and apply Python source updates
python updater.py


:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH. 
    echo Please install Python 3.9+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Check if .venv exists, create if not
if not exist ".venv\Scripts\activate.bat" (
    echo [INFO] Creating Python virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate the virtual environment
call .venv\Scripts\activate.bat

:: Install/Update Requirements
echo [INFO] Checking dependencies...
pip install -q -r requirements.txt

:: Check for outdated packages
pip list --outdated > .outdated.tmp 2>nul
for /f %%i in (".outdated.tmp") do set size=%%~zi
if !size! gtr 0 (
    echo.
    echo [INFO] Updates are available for your dependencies:
    type .outdated.tmp
    echo.
    set /p update_deps="Would you like to install these updates? (y/N): "
    if /i "!update_deps!"=="y" (
        echo [INFO] Updating dependencies...
        python -m pip install --upgrade -q -r requirements.txt
    )
)
if exist ".outdated.tmp" del ".outdated.tmp"

:: Run the quiz
echo.
echo [INFO] Starting the game...
echo =======================================================
echo.
python main.py

echo.
echo =======================================================
pause
