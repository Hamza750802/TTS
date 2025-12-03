# IndexTTS2 Server for CheapTTS

High-quality zero-shot TTS with emotion control. Runs on Vast.ai GPU instance.

## Requirements

| Resource | Requirement |
|----------|-------------|
| **GPU VRAM** | ~4-6GB (FP16 mode) |
| **Disk** | ~15GB (model + voices) |
| **CUDA** | 12.4+ |

**Recommended GPUs:** RTX 3090, RTX 4090, A10, A40

## Quick Start (Vast.ai)

### 1. Create a Vast.ai Instance

- **Image:** `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime`
- **GPU:** RTX 3090 or RTX 4090 (cheapest options with enough VRAM)
- **Disk:** 50GB
- **Expose port:** 8000

### 2. SSH into the instance and run:

```bash
# Clone CheapTTS repo
git clone https://github.com/Hamza750802/TTS.git
cd TTS/indextts-server

# Run the setup script
chmod +x setup.sh
./setup.sh
```

Or manually:

```bash
# Install git-lfs
apt-get update && apt-get install -y git-lfs ffmpeg libsndfile1

# Clone IndexTTS2
git clone https://github.com/index-tts/index-tts.git
cd index-tts
git lfs install && git lfs pull

# Install with uv (recommended) or pip
pip install uv
uv sync --extra webui

# Or with pip
pip install -e .

# Download model
pip install "huggingface-hub[cli,hf_xet]"
huggingface-cli download IndexTeam/IndexTTS-2 --local-dir=checkpoints

# Go back and start server
cd ..
pip install fastapi uvicorn python-multipart
python server.py
```

### 3. Add Voice References

Upload WAV files (5-30 seconds each) to the `voices/` directory:

```bash
# Create voices directory
mkdir -p voices

# Upload your voice files
# Example: voices/Emily.wav, voices/Michael.wav, etc.

# Run setup to create voice entries
python setup_voices.py
```

### 4. Set Environment Variable on Railway

```
INDEXTTS_URL=http://YOUR-VAST-IP:8000
```

## API Endpoints

### Health Check
```
GET /
GET /health
```

### List Voices
```
GET /voices
```

Response:
```json
{
  "success": true,
  "voices": [
    {"id": "Emily", "name": "Emily", "type": "audio"},
    {"id": "Michael", "name": "Michael", "type": "audio"}
  ],
  "count": 2
}
```

### Generate Speech
```
POST /generate
Content-Type: application/json

{
  "text": "Hello, welcome to CheapTTS!",
  "voice": "Emily",
  "emo_alpha": 0.6,
  "use_emo_text": false
}
```

Response: WAV audio file

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | string | required | Text to synthesize |
| `voice` | string | "Emily" | Voice name |
| `emo_alpha` | float | 0.6 | Emotion intensity (0.0-1.0) |
| `use_emo_text` | bool | false | Infer emotion from text |
| `emo_text` | string | null | Separate emotion description |
| `emo_vector` | float[8] | null | Direct emotion control |
| `use_random` | bool | false | Enable stochastic sampling |

### Emotion Vector Format

`[happy, angry, sad, afraid, disgusted, melancholic, surprised, calm]`

Example: `[0.8, 0, 0, 0, 0, 0, 0.2, 0]` = happy + slightly surprised

### Upload Voice
```
POST /upload-voice
Content-Type: multipart/form-data

file: <audio file>
name: "CustomVoice"
```

## Voice File Requirements

- **Format:** WAV (16-bit PCM recommended), MP3, or FLAC
- **Duration:** 5-30 seconds of clear speech
- **Quality:** Clean recording, minimal background noise
- **Content:** Natural conversational speech

### Voice Quality Tips

- 5-10 seconds: Works, basic cloning
- 20-30 seconds: Good quality
- 60+ seconds: Excellent quality
- 2-3 minutes: Professional grade

## Emotion Control Examples

### Using Text Emotion
```json
{
  "text": "I can't believe we won!",
  "voice": "Emily",
  "use_emo_text": true,
  "emo_alpha": 0.7
}
```

### Using Emotion Description
```json
{
  "text": "The results are in.",
  "voice": "Emily",
  "use_emo_text": true,
  "emo_text": "excited and surprised",
  "emo_alpha": 0.6
}
```

### Using Emotion Vector
```json
{
  "text": "I'm so sorry for your loss.",
  "voice": "Emily",
  "emo_vector": [0, 0, 0.8, 0, 0, 0.2, 0, 0],
  "emo_alpha": 0.7
}
```

## Keeping the Server Running

```bash
# Using tmux
tmux new -s indextts
python server.py
# Press Ctrl+B, then D to detach

# Reattach later
tmux attach -t indextts
```

Or use nohup:
```bash
nohup python server.py > server.log 2>&1 &
```

## Docker Deployment

```bash
# Build
docker build -t indextts-server .

# Run
docker run -d --gpus all -p 8000:8000 -v $(pwd)/voices:/app/voices indextts-server
```

## Troubleshooting

### "Model not loaded"
- Wait 30-60 seconds for model to load on startup
- Check logs for CUDA errors

### "Voice not found"
- Ensure voice WAV file exists in voices/
- Check filename matches exactly (case-sensitive)
- Run `python setup_voices.py` to update entries

### Slow generation
- Ensure GPU is being used (check nvidia-smi)
- FP16 mode should be enabled by default
- First generation is slower (model warmup)

### Out of memory
- Use FP16 mode (default)
- Restart server to clear VRAM
- Use a GPU with more VRAM
