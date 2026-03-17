#!/usr/bin/env bash

# Change to the directory of the script
cd "$(dirname "$0")"

echo "======================================================="
echo "         WW1 & WW2 Agentic Trivia CLI Setup"
echo "======================================================="

# OTA Update for the Offline Knowledge Bank
OTA_URL="https://raw.githubusercontent.com/adityasricharan/wwq/master/questions.enc"
if [ -n "$OTA_URL" ]; then
    if curl -s --head -f "$OTA_URL" >/dev/null 2>&1; then
        if [ -f "questions.enc.official" ]; then
            # User has a custom bank active — update official backup only
            echo "[INFO] Checking for official knowledge bank updates..."
            curl -s -L -o "questions.enc.official.tmp" "$OTA_URL"
            if [ -f "questions.enc.official.tmp" ]; then
                mv "questions.enc.official.tmp" "questions.enc.official"
                echo "[INFO] Official bank updated in background. Your custom bank is unchanged."
            fi
        else
            # User is on official bank — update questions.enc directly
            echo "[INFO] Checking for offline knowledge bank updates..."
            curl -s -L -o "questions.enc.tmp" "$OTA_URL"
            if [ -f "questions.enc.tmp" ]; then
                mv "questions.enc.tmp" "questions.enc"
                echo "[INFO] Knowledge bank updated successfully."
            fi
        fi
    fi
fi

# Code OTA — check for and apply Python source updates
python3 updater.py


# Check if python3 is installed
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed or not in your PATH."
    echo "Please install Python 3.9+ from https://www.python.org/downloads/"
    echo "Press Enter to exit..."
    read -r
    exit 1
fi

# Check if .venv exists, create if not
if [ ! -f ".venv/bin/activate" ]; then
    echo "[INFO] Creating Python virtual environment..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create virtual environment."
        echo "Press Enter to exit..."
        read -r
        exit 1
    fi
fi

# Activate the virtual environment
source .venv/bin/activate

# Install/Update requirements
echo "[INFO] Checking dependencies..."
pip install -q -r requirements.txt

# Check for outdated packages
pip list --outdated > .outdated.tmp 2>/dev/null
if [ -s .outdated.tmp ]; then
    echo ""
    echo "[INFO] Updates are available for your dependencies:"
    cat .outdated.tmp
    echo ""
    read -p "Would you like to install these updates? (y/N): " update_deps
    if [[ "$update_deps" =~ ^[Yy]$ ]]; then
        echo "[INFO] Updating dependencies..."
        python3 -m pip install --upgrade -q -r requirements.txt
    fi
fi
rm -f .outdated.tmp
# Run the quiz
echo ""
echo "[INFO] Starting the game..."
echo "======================================================="
echo ""
python3 main.py

echo ""
echo "======================================================="
echo "Press Enter to exit..."
read -r
