#!/bin/bash
set -e

echo ""
echo "============================================"
echo "  AI Job Search Assistant — Startup Script"
echo "============================================"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "[ERROR] Python 3 not found. Install from https://python.org"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Install dependencies
echo "[1/3] Installing backend dependencies..."
cd "$SCRIPT_DIR/backend"
pip3 install -r requirements.txt -q

# Start backend
echo "[2/3] Starting backend API on port 8000..."
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!
sleep 2

# Open frontend
echo "[3/3] Opening frontend in browser..."
if command -v open &>/dev/null; then
  open "$SCRIPT_DIR/frontend/index.html"       # macOS
elif command -v xdg-open &>/dev/null; then
  xdg-open "$SCRIPT_DIR/frontend/index.html"   # Linux
else
  echo "Open manually: $SCRIPT_DIR/frontend/index.html"
fi

echo ""
echo "✅ Running!"
echo "   Backend API : http://localhost:8000"
echo "   API Docs    : http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop the backend."
wait $BACKEND_PID
