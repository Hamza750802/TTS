#!/bin/bash
# ============================================================
# Studio Model TTS - One-Command Deployment Script
# ============================================================
# Usage: curl -sSL https://raw.githubusercontent.com/Hamza750802/TTS/master/vibevoice-server/deploy.sh | bash
# Or: ./deploy.sh
# ============================================================

set -e

echo "=============================================="
echo "  Studio Model TTS - Automated Deployment"
echo "=============================================="

cd ~

# 1. Install dependencies
echo "[1/7] Installing Python dependencies..."
pip install -q fastapi uvicorn scipy diffusers accelerate tiktoken protobuf huggingface_hub librosa soundfile
pip install -q transformers==4.51.3  # VV requires this specific version

# 2. Clone VV repository (with patches already applied)
echo "[2/7] Setting up VV library..."
if [ ! -d "VV" ]; then
    git clone --depth 1 https://github.com/Hamza750802/VV.git
fi

# 3. Apply patches to VV processor (fixes tokenizer loading)
echo "[3/7] Applying patches..."
python3 << 'PATCH'
import os
f = open(os.path.expanduser('~/VV/vibevoice/processor/vibevoice_processor.py'), 'r')
content = f.read()
f.close()

# Patch 1: Use model path for tokenizer
if 'language_model_pretrained_name = config.get' in content:
    content = content.replace(
        'language_model_pretrained_name = config.get',
        'language_model_pretrained_name = pretrained_model_name_or_path  # config.get',
        1
    )

# Patch 2: Skip qwen check
if "if 'qwen' in language_model_pretrained_name.lower():" in content:
    content = content.replace(
        "if 'qwen' in language_model_pretrained_name.lower():",
        "if True:  # 'qwen' in language_model_pretrained_name.lower():",
        1
    )

f = open(os.path.expanduser('~/VV/vibevoice/processor/vibevoice_processor.py'), 'w')
f.write(content)
f.close()
print("Patches applied!")
PATCH

# 4. Download server file from GitHub
echo "[4/7] Downloading server..."
if [ ! -f "server_1.5b.py" ]; then
    curl -sSL https://raw.githubusercontent.com/Hamza750802/TTS/master/vibevoice-server/server_1.5b.py -o server_1.5b.py
fi

# 5. Download custom voices from HuggingFace
echo "[5/7] Downloading custom voices..."
mkdir -p voices
python3 << 'VOICES'
from huggingface_hub import hf_hub_download, list_repo_files
import os

os.makedirs('voices', exist_ok=True)

# Get all WAV files from the repo
try:
    files = list_repo_files("hmzh59/vibevoice-voices")
    wav_files = [f for f in files if f.endswith('.wav')]
    
    for filename in wav_files:
        try:
            path = hf_hub_download(
                repo_id="hmzh59/vibevoice-voices",
                filename=filename,
                local_dir="./voices",
                local_dir_use_symlinks=False
            )
            print(f"  ✓ {filename}")
        except Exception as e:
            print(f"  ✗ {filename}: {e}")
    
    print(f"\nDownloaded {len(wav_files)} voice files")
except Exception as e:
    print(f"Error listing files: {e}")
VOICES

# 6. Pre-download model (optional, will download on first run anyway)
echo "[6/7] Pre-caching model from HuggingFace..."
python3 << 'PRELOAD'
from huggingface_hub import snapshot_download
print("Downloading VibeVoice-1.5B model...")
snapshot_download(
    repo_id="hmzh59/vibevoice-models",
    allow_patterns=["VibeVoice-1.5B/**"],
    local_dir_use_symlinks=False
)
print("Model cached!")
PRELOAD

# 7. Create start script
echo "[7/7] Creating start script..."
cat > start.sh << 'START'
#!/bin/bash
cd ~
export PYTHONPATH=~/VV
python3 server_1.5b.py
START
chmod +x start.sh

echo ""
echo "=============================================="
echo "  ✅ Deployment Complete!"
echo "=============================================="
echo ""
echo "To start the server:"
echo "  ./start.sh"
echo ""
echo "Or manually:"
echo "  export PYTHONPATH=~/VV"
echo "  python3 server_1.5b.py"
echo ""
echo "Server will run on port 8070"
echo "=============================================="
