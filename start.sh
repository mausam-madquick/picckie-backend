#!/bin/bash

# Force Python to output stdout and stderr immediately without buffering
export PYTHONUNBUFFERED=1

# Limit ONNX/OpenMP/MKL to 1 thread to avoid OOM crashes on Render's Free tier
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

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

