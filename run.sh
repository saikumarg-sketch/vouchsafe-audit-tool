#!/bin/bash
# Vouchsafe — one-click launcher for macOS / Linux
# Make executable once with: chmod +x run.sh
# Then double-click or run ./run.sh

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "First-time setup: creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "Installing dependencies..."
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo ""
echo "Starting Vouchsafe..."
echo "Press Ctrl+C in this window to stop."
echo ""
streamlit run app.py
