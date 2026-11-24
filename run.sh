#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# DUAL-BOT CONTROLLER — TERMUX & LINUX ONE-CLICK LAUNCH SCRIPT
# ═══════════════════════════════════════════════════════════════════════════════

echo "==========================================================="
echo " 🤖 Starting Dual-Bot Command Center & Telegram Engines"
echo "==========================================================="

# Check python
if command -v python3 &>/dev/null; then
    PY_CMD="python3"
elif command -v python &>/dev/null; then
    PY_CMD="python"
else
    echo "❌ Python is not installed. In Termux, type: pkg install python"
    exit 1
fi

# Ensure required libraries
echo "🔍 Checking dependencies..."
$PY_CMD -c "import requests, bs4, dotenv" &>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 Installing required python packages..."
    pip install requests beautifulsoup4 python-dotenv python-telegram-bot
fi

# Set default port if not set
export PORT=${PORT:-8080}

echo "🚀 Launching Application on http://localhost:$PORT ..."
echo "🌐 Open your browser at http://localhost:$PORT or http://127.0.0.1:$PORT"
echo "==========================================================="

$PY_CMD app.py
