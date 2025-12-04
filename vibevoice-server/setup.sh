#!/bin/bash
# Setup script for Podcast TTS server on Vast.ai GPU instance
# Run this after SSH-ing into the instance

set -e

echo "==================================="
echo "Podcast TTS Server Setup for CheapTTS"
echo "==================================="

# Update and install dependencies
echo "[1/7] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq git wget curl ffmpeg > /dev/null 2>&1

# Clone VibeVoice if not exists
echo "[2/7] Cloning VibeVoice repository..."
if [ ! -d "VibeVoice" ]; then
    git clone --depth 1 https://github.com/microsoft/VibeVoice.git
fi

# Install Python dependencies
echo "[3/7] Installing Python dependencies..."
cd VibeVoice
pip install --quiet -e .

# Install additional dependencies
pip install --quiet fastapi uvicorn[standard]

# Create directories
echo "[4/7] Creating directories..."
cd ..
mkdir -p voices/streaming_model outputs temp

# Download voice presets
echo "[5/7] Downloading voice presets..."
# VibeVoice presets are in the demo/voices/streaming_model directory
if [ -d "VibeVoice/demo/voices/streaming_model" ]; then
    cp -r VibeVoice/demo/voices/streaming_model/* voices/streaming_model/
    echo "Copied voice presets from VibeVoice repo"
else
    echo "Voice presets not found in repo, downloading from HuggingFace..."
    # Try to download from HuggingFace
    python3 -c "
from huggingface_hub import snapshot_download
import os

# Download model files (includes voice presets)
model_path = snapshot_download(
    repo_id='microsoft/VibeVoice-Realtime-0.5B',
    local_dir='./model',
    local_dir_use_symlinks=False
)
print(f'Downloaded model to {model_path}')
" || echo "Note: Manual voice preset download may be needed"
fi

# Copy server files
echo "[6/7] Setting up server..."
# Copy server.py to current directory if not already there
if [ ! -f "server.py" ]; then
    echo "Please copy server.py to this directory"
fi

# Install cloudflared for tunnel
echo "[7/7] Installing cloudflared..."
if ! command -v cloudflared &> /dev/null; then
    curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
    chmod +x /usr/local/bin/cloudflared
fi

echo ""
echo "==================================="
echo "Setup complete!"
echo "==================================="
echo ""
echo "To start the server:"
echo "  export MODEL_PATH=microsoft/VibeVoice-Realtime-0.5B"
echo "  export MODEL_DEVICE=cuda"
echo "  python server.py"
echo ""
echo "To expose via cloudflare tunnel:"
echo "  cloudflared tunnel --url http://localhost:8080"
echo ""
echo "Or use the direct port mapping if configured in Vast.ai"
