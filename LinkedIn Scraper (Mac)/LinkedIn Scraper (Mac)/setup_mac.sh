#!/bin/bash
# ── LinkedIn Scraper — First-Time Mac Setup ────────────────────────────────────
# Run this once before using the scraper.
# Double-click it in Finder (you may need to right-click → Open the first time).

set -e

cd "$(dirname "$0")"

echo ""
echo "================================================"
echo "  LinkedIn Recruiter Scraper — Mac Setup"
echo "================================================"
echo ""

# ── Check Python 3 ────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 is not installed."
    echo ""
    echo "Please install it from: https://www.python.org/downloads/"
    echo "Then run this setup script again."
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

PY_VERSION=$(python3 --version 2>&1)
echo "[OK] $PY_VERSION found"
echo ""

# ── Create virtual environment ────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# ── Install dependencies ──────────────────────────────────────────────────────
echo "Installing required packages (this may take a minute)..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo ""
echo "Installing Playwright browser (Chromium)..."
playwright install chromium

echo ""
echo "================================================"
echo "  Setup complete!"
echo ""
echo "  To run the scraper, double-click:"
echo "    'Launch Scraper.command'"
echo "================================================"
echo ""
read -p "Press Enter to close..."
