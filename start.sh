#!/bin/bash

# Start the Python FastAPI background remover in the background
echo "[*] Starting Python FastAPI background remover on port 8000..."
cd /app/python-bg-remover
uvicorn app:app --host 127.0.0.1 --port 8000 &

# Start the Node.js Express server in the foreground
# It will listen on the port injected by Render ($PORT)
echo "[*] Starting Express Gateway on port ${PORT:-8001}..."
cd /app/server
node server.js
