# Use a pre-configured slim image containing both Node.js and Python
FROM nikolaik/python-nodejs:python3.10-nodejs20-slim

WORKDIR /app

# Set a persistent, static directory for the rembg u2net model cache
ENV U2NET_HOME=/app/.u2net

# Install basic system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements first for caching
COPY python-bg-remover/requirements.txt python-bg-remover/
RUN pip install --no-cache-dir -r python-bg-remover/requirements.txt

# Pre-download the u2net model for rembg so it does not cause API timeouts on first run
RUN echo "[*] Downloading rembg u2net model during build..." && \
    python -c "from rembg import remove; import numpy as np; from PIL import Image; remove(Image.new('RGBA', (1, 1)))"

# Copy Node.js dependencies for caching
COPY server/package.json server/
RUN cd server && npm install

# Copy all project files
COPY . .

# Convert line endings of start.sh to Unix format if built on Windows and make executable
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

# Run start script
CMD ["bash", "start.sh"]
