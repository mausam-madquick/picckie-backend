#!/bin/bash

# Force Python to output stdout and stderr immediately without buffering
export PYTHONUNBUFFERED=1

# Start the Python FastAPI background remover in the background
# Redirect both stdout and stderr to /tmp/python.log so we can debug it
echo "[*] Starting Python FastAPI background remover on port 8000..."
cd /app/python-bg-remover
python3 -m uvicorn app:app --host 127.0.0.1 --port 8000 > /tmp/python.log 2>&1 &


# Start the Node.js Express server in the foreground
# It will listen on the port injected by Render ($PORT)
echo "[*] Starting Express Gateway on port ${PORT:-8001}..."
cd /app/server
node server.js

