#!/bin/bash
# IndexTTS2 Server Setup Script for Vast.ai
# Run this after SSH into your Vast.ai instance

set -e

echo "=========================================="
echo "IndexTTS2 Server Setup for CheapTTS"
echo "=========================================="

# Install system dependencies
echo "[1/6] Installing system dependencies..."
apt-get update
apt-get install -y git git-lfs ffmpeg libsndfile1 curl wget

# Clone IndexTTS2
echo "[2/6] Cloning IndexTTS2..."
if [ ! -d "index-tts" ]; then
    git clone https://github.com/index-tts/index-tts.git
    cd index-tts
    git lfs install
    git lfs pull
    cd ..
fi

# Install Python dependencies
echo "[3/6] Installing Python dependencies..."
pip install --upgrade pip
pip install uv

cd index-tts
uv sync --extra webui || pip install -e .
cd ..

# Download model
echo "[4/6] Downloading IndexTTS2 model (~10GB)..."
pip install "huggingface-hub[cli,hf_xet]"
cd index-tts
huggingface-cli download IndexTeam/IndexTTS-2 --local-dir=checkpoints
cd ..

# Install server dependencies
echo "[5/6] Installing server dependencies..."
pip install fastapi uvicorn python-multipart pydantic

# Create directories
echo "[6/6] Setting up directories..."
mkdir -p voices embeddings outputs temp

# Add indextts to Python path
export PYTHONPATH="$(pwd)/index-tts:$PYTHONPATH"
echo "export PYTHONPATH=\"$(pwd)/index-tts:\$PYTHONPATH\"" >> ~/.bashrc

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "NEXT STEPS:"
echo ""
echo "1. Add voice reference files to voices/"
echo "   Example: voices/Emily.wav (5-30 seconds of speech)"
echo ""
echo "2. Run voice setup:"
echo "   python setup_voices.py"
echo ""
echo "3. Start the server:"
echo "   python server.py"
echo ""
echo "Server will run on port 8000"
echo "=========================================="
