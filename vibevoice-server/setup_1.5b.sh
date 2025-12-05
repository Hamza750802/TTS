#!/bin/bash
# Setup script for Studio Model TTS Server (1.5B) on Vast.ai GPU instance
# Run this after SSH-ing into the instance

set -e

echo "==================================="
echo "Studio Model TTS Server Setup"
echo "VibeVoice-1.5B for CheapTTS"
echo "==================================="

# Update and install dependencies
echo "[1/8] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq git wget curl ffmpeg > /dev/null 2>&1

# Install Python dependencies first
echo "[2/8] Installing Python dependencies..."
pip install --quiet torch torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install --quiet transformers accelerate huggingface_hub
pip install --quiet fastapi uvicorn[standard] scipy numpy

# Clone VV package (vibevoice modular implementation)
echo "[3/8] Cloning VV repository..."
if [ ! -d "VV" ]; then
    git clone --depth 1 https://github.com/Hamza750802/VV.git
fi
# Add VV to Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/VV"
echo 'export PYTHONPATH="${PYTHONPATH}:$(pwd)/VV"' >> ~/.bashrc

# Create directories
echo "[4/8] Creating directories..."
mkdir -p voices outputs temp model

# Download VibeVoice-1.5B model from HuggingFace
echo "[5/8] Downloading VibeVoice-1.5B model (~5.4GB)..."
python3 -c "
from huggingface_hub import snapshot_download
import os

print('Downloading VibeVoice-1.5B model...')
model_path = snapshot_download(
    repo_id='hmzh59/vibevoice-models',
    allow_patterns=['VibeVoice-1.5B/**'],
    local_dir='./model',
    local_dir_use_symlinks=False
)
print(f'Downloaded model to {model_path}')
"

# Download built-in voice presets (7 voices)
echo "[6/8] Downloading built-in voice presets..."
python3 -c "
from huggingface_hub import hf_hub_download
import os

voices = ['Carter', 'Davis', 'Emma', 'Frank', 'Grace', 'Mike', 'Samuel']
os.makedirs('voices', exist_ok=True)

for voice in voices:
    print(f'Downloading {voice}...')
    try:
        hf_hub_download(
            repo_id='hmzh59/vibevoice-models',
            filename=f'VibeVoice-1.5B/voices/{voice}.wav',
            local_dir='./model',
            local_dir_use_symlinks=False
        )
        # Copy to voices directory
        src = f'./model/VibeVoice-1.5B/voices/{voice}.wav'
        if os.path.exists(src):
            import shutil
            shutil.copy(src, f'./voices/{voice}.wav')
            print(f'  -> voices/{voice}.wav')
    except Exception as e:
        print(f'  Warning: Could not download {voice}: {e}')

print('Done downloading built-in voices.')
"

# Copy custom voices if they exist on the host
echo "[7/8] Setting up custom voices directory..."
echo "To add custom voices, copy .wav files to the 'voices/' directory."
echo "Supported custom voices: Adam, Aloy, Bill, Chris, Dace, Emily, Grace, Hannah, Jennifer, John, Michael, Natalie, Oliva, Sean, Sophia"

# Copy server file
echo "[8/8] Setting up server..."
if [ -f "server_1.5b.py" ]; then
    echo "Server file ready: server_1.5b.py"
else
    echo "WARNING: server_1.5b.py not found. Please copy it to this directory."
fi

echo ""
echo "==================================="
echo "Setup Complete!"
echo "==================================="
echo ""
echo "To start the server:"
echo "  export PYTHONPATH=\"\${PYTHONPATH}:\$(pwd)/VV\""
echo "  export MODEL_PATH=./model/VibeVoice-1.5B"
echo "  python server_1.5b.py"
echo ""
echo "To create a public URL (optional):"
echo "  cloudflared tunnel --url http://localhost:8080"
echo ""
echo "Available voices:"
ls -1 voices/*.wav 2>/dev/null | xargs -I{} basename {} .wav || echo "  (none yet - copy .wav files to voices/)"
echo ""
