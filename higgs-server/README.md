# HiggsAudio v2 TTS Server

Premium multi-speaker dialogue TTS powered by [HiggsAudio v2](https://github.com/boson-ai/higgs-audio).

## Requirements

- **GPU**: NVIDIA with **24GB+ VRAM** (RTX 4090, A6000, A100, etc.)
- **CUDA**: 12.x (included in NVIDIA Docker image)

## Quick Start on Vast.ai

### 1. Rent a GPU Instance

On [vast.ai](https://vast.ai), search for:
- **GPU**: RTX 4090, A6000, or A100 (24GB+ VRAM)
- **Image**: `nvcr.io/nvidia/pytorch:25.02-py3`
- **Disk**: 50GB+ (for model weights)

### 2. SSH into the Instance

```bash
ssh -p <port> root@<instance-ip>
```

### 3. Clone and Setup

```bash
# Clone TTS repo
git clone https://github.com/Hamza750802/TTS.git
cd TTS/higgs-server

# Or just copy the files
mkdir -p /app && cd /app

# Clone HiggsAudio
git clone https://github.com/boson-ai/higgs-audio.git
cd higgs-audio
pip install -r requirements.txt
pip install -e .
cd ..

# Install server dependencies
pip install fastapi uvicorn[standard] python-multipart aiofiles

# Copy server.py to /app
# (Upload from this repo or copy-paste)
```

### 4. Pre-download Models (Recommended)

```bash
python preload_model.py
```

This downloads ~12GB of model weights from HuggingFace.

### 5. Run the Server

```bash
python server.py
```

Server runs on port 8000 by default.

### 6. Open the Port

Make sure port 8000 is exposed in your Vast.ai instance settings.

## Docker Deployment (Alternative)

```bash
# Build
docker build -t higgs-server .

# Run
docker run --gpus all -p 8000:8000 -v /path/to/reference_audio:/app/reference_audio higgs-server
```

## API Endpoints

### Health Check
```bash
GET /health
```

### Generate Single Speaker Audio
```bash
POST /generate
Content-Type: application/json

{
  "text": "Hello, this is a test.",
  "temperature": 0.3,
  "top_p": 0.95,
  "reference_audio_id": "optional_voice_id"
}
```

### Generate Multi-Speaker Dialogue
```bash
POST /multi-speaker
Content-Type: application/json

{
  "text": "[Speaker1]: Hello, how are you?\n[Speaker2]: I'm doing great!",
  "temperature": 0.3,
  "seed": 12345
}
```

The model automatically assigns distinct voices to each speaker.

### Upload Reference Audio (Voice Cloning)
```bash
POST /upload-reference
Content-Type: multipart/form-data

file: <audio_file.wav>
voice_id: my_custom_voice (optional)
```

### List Reference Audios
```bash
GET /list-references
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HIGGS_MODEL_PATH` | `bosonai/higgs-audio-v2-generation-3B-base` | Model path |
| `HIGGS_TOKENIZER_PATH` | `bosonai/higgs-audio-v2-tokenizer` | Tokenizer path |
| `HIGGS_DEVICE` | `cuda` | Device (cuda/cpu) |
| `HIGGS_MAX_WORKERS` | `2` | Concurrent generation threads |
| `PORT` | `8000` | Server port |

## Integration with CheapTTS

Once running, set this in your Railway environment:

```
HIGGS_SERVER_URL=http://<vast-ip>:<port>
```

Then the webapp will use HiggsAudio for premium multi-speaker dialogue.

## Performance

- **Startup**: ~60-120s (model loading)
- **Generation**: ~2-5s for short text, longer for multi-speaker
- **VRAM Usage**: ~20-22GB

## Troubleshooting

### Out of Memory
- Ensure you have 24GB+ VRAM
- Reduce `max_new_tokens` in requests
- Use one generation at a time

### Model Download Fails
- Check HuggingFace connectivity
- Try `huggingface-cli login` if gated model

### Audio Quality Issues
- Use `temperature=0.3` for consistent quality
- Add `seed` for reproducibility
