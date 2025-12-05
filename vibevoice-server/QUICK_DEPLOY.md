# Studio Model TTS Server - Quick Deployment Guide

## One-Command Deployment (Future Instances)

SSH into your new Vast.ai instance and run:

```bash
curl -sSL https://raw.githubusercontent.com/Hamza750802/TTS/master/vibevoice-server/deploy.sh | bash
```

That's it! The script will:
1. ✅ Install all Python dependencies (fastapi, transformers==4.51.3, librosa, etc.)
2. ✅ Clone and patch the VV library
3. ✅ Download server_1.5b.py from GitHub
4. ✅ Download all 15 voice samples from HuggingFace
5. ✅ Pre-cache the VibeVoice-1.5B model
6. ✅ Create a start.sh script

## Start the Server

```bash
./start.sh
```

Or manually:
```bash
export PYTHONPATH=~/VV
python3 server_1.5b.py
```

## Server Details

- **Port**: 8070
- **Voices**: 21 total (15 custom + 6 VV demo)
- **Model**: VibeVoice-1.5B from `hmzh59/vibevoice-models`
- **Voice samples**: From `hmzh59/vibevoice-voices`

## API Endpoints

### Generate Audio
```bash
curl -X POST http://localhost:8070/generate \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice": "adam"}' \
  -o output.wav
```

### List Voices
```bash
curl http://localhost:8070/voices
```

### Health Check
```bash
curl http://localhost:8070/health
```

## Vast.ai Instance Requirements

- **GPU**: RTX 4080 or better (16GB+ VRAM)
- **Disk**: 30GB+
- **Template**: PyTorch 2.x + CUDA 12.1
- **Open ports**: 8070

## Expose with Cloudflare Tunnel

```bash
# Install cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared

# Create tunnel (gives you a public URL)
./cloudflared tunnel --url http://localhost:8070
```

## Adding New Voices

1. Upload WAV file to server: `scp -P PORT voice.wav root@HOST:~/voices/`
2. Restart server
3. The voice will be available with the filename (without extension) as the voice name

## Troubleshooting

### "transformers version mismatch"
```bash
pip install transformers==4.51.3
```

### "No module named 'librosa'"
```bash
pip install librosa soundfile
```

### Model loading fails
Clear HuggingFace cache and re-download:
```bash
rm -rf ~/.cache/huggingface/hub/models--hmzh59--vibevoice-models
python3 -c "from huggingface_hub import snapshot_download; snapshot_download('hmzh59/vibevoice-models', allow_patterns=['VibeVoice-1.5B/**'])"
```
