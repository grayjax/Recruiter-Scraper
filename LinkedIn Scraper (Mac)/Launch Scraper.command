#!/bin/bash
# ── LinkedIn Scraper — Mac Launcher ───────────────────────────────────────────
# Double-click this file to launch the scraper.
# Run setup_mac.sh first if this is your first time.

cd "$(dirname "$0")"

# Use the virtual environment if it exists, otherwise fall back to system Python
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

python3 gui_app.py

# If it fails, show an error message and pause
if [ $? -ne 0 ]; then
    echo ""
    echo "Failed to launch. Have you run setup_mac.sh?"
    echo ""
    read -p "Press Enter to close..."
fi
