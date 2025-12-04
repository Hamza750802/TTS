#!/bin/bash
# HiggsAudio v2 Server - One-Line Setup for Vast.ai
# Run: curl -sSL https://raw.githubusercontent.com/Hamza750802/TTS/main/higgs-server/setup.sh | bash

set -e

echo "=============================================="
echo "  HiggsAudio v2 Server Setup"
echo "  Requires: 24GB+ VRAM GPU"
echo "=============================================="

# Create app directory
mkdir -p /app/reference_audio
cd /app

# Clone HiggsAudio
echo "[1/5] Cloning HiggsAudio repository..."
if [ ! -d "higgs-audio" ]; then
    git clone https://github.com/boson-ai/higgs-audio.git
fi

# Install HiggsAudio
echo "[2/5] Installing HiggsAudio..."
cd higgs-audio
pip install -q -r requirements.txt
pip install -q -e .
cd ..

# Install server dependencies
echo "[3/5] Installing server dependencies..."
pip install -q fastapi uvicorn[standard] python-multipart aiofiles

# Download server files
echo "[4/5] Downloading server files..."
curl -sSL -o server.py https://raw.githubusercontent.com/Hamza750802/TTS/main/higgs-server/server.py
curl -sSL -o preload_model.py https://raw.githubusercontent.com/Hamza750802/TTS/main/higgs-server/preload_model.py

# Pre-download models
echo "[5/5] Pre-downloading models (this may take a few minutes)..."
python preload_model.py

echo ""
echo "=============================================="
echo "  Setup Complete!"
echo "=============================================="
echo ""
echo "To start the server, run:"
echo "  cd /app && python server.py"
echo ""
echo "Server will be available at: http://0.0.0.0:8000"
echo ""
echo "Make sure port 8000 is exposed in Vast.ai settings!"
echo ""
