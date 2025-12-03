# IndexTTS2 Server for CheapTTS

High-quality zero-shot TTS with emotion control and **instant cached voice embeddings**. Runs on Vast.ai GPU instance.

## Requirements

| Resource | Requirement |
|----------|-------------|
| **GPU VRAM** | ~4-6GB (FP16 mode) |
| **Disk** | ~15GB (model + voices) |
| **CUDA** | 12.4+ |

**Recommended GPUs:** RTX 3090, RTX 4090, A10, A40

---

## Quick Start (Vast.ai)

### Step 1: Create a Vast.ai Instance

1. Go to [vast.ai](https://vast.ai) and create an account
2. Search for template: `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime`
3. Settings:
   - **GPU:** RTX 3090 or RTX 4090 (cheapest with enough VRAM)
   - **Disk:** 50GB minimum
   - **Expose port:** 8000
4. Launch the instance and wait for it to start

### Step 2: SSH into the instance and run setup

```bash
# Clone CheapTTS repo
git clone https://github.com/Hamza750802/TTS.git
cd TTS/indextts-server

# Run the setup script
chmod +x setup.sh
./setup.sh
```

This will:
- Install dependencies (git-lfs, ffmpeg, etc.)
- Clone IndexTTS2 repository
- Download the model checkpoints (~10GB)
- Start the server on port 8000

---

## Adding Voice Presets

### Option 1: Upload via API (Recommended)

**Single voice upload:**
```bash
curl -X POST http://YOUR-VAST-IP:8000/upload-voice \
  -F "file=@emily.wav" \
  -F "name=Emily"
```

**Bulk upload via ZIP:**
```bash
# Create a ZIP with all your voice files
# voices.zip containing: emily.wav, michael.wav, sarah.wav, etc.

curl -X POST http://YOUR-VAST-IP:8000/upload-voices-zip \
  -F "file=@voices.zip" \
  -F "cache_immediately=true"
```

The server will:
1. Save each audio file to `/voices/`
2. Extract speaker embedding (takes ~5-10 seconds per voice)
3. Cache embedding to `/cache/` for instant reuse

### Option 2: SCP/SFTP Upload

```bash
# Upload files directly to the voices folder
scp emily.wav root@YOUR-VAST-IP:/root/TTS/indextts-server/voices/
scp michael.wav root@YOUR-VAST-IP:/root/TTS/indextts-server/voices/

# Then cache all voices
curl -X POST http://YOUR-VAST-IP:8000/cache-all
```

### Option 3: Mount a Volume with Pre-existing Voices

When starting the Docker container, mount a volume:
```bash
docker run -d --gpus all -p 8000:8000 \
  -v /path/to/your/voices:/app/voices \
  -v /path/to/cache:/app/cache \
  indextts-server
```

---

## Voice File Requirements

| Requirement | Details |
|-------------|---------|
| **Format** | WAV (16-bit PCM), MP3, or FLAC |
| **Duration** | 5-30 seconds ideal |
| **Quality** | Clean recording, minimal background noise |
| **Content** | Natural conversational speech |
| **Sample Rate** | 16kHz or higher (will be resampled) |

### Voice Quality Tips

| Duration | Quality |
|----------|---------|
| 5-10 seconds | Basic cloning |
| 20-30 seconds | Good quality |
| 60+ seconds | Excellent quality |

---

## API Endpoints

### Health Check
```
GET /
GET /health
```

### List All Voices
```
GET /voices
```

Response:
```json
{
  "success": true,
  "voices": [
    {"id": "Emily", "name": "Emily", "cached": true, "status": "ready"},
    {"id": "Michael", "name": "Michael", "cached": false, "status": "will_cache_on_first_use"}
  ],
  "count": 2,
  "cached_count": 1
}
```

### Get Voice Info
```
GET /voice/{voice_name}/info
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

**First generation with a new voice:** Takes ~10-15 seconds (extracting + caching embedding)
**Subsequent generations:** Takes ~2-5 seconds (uses cached embedding)

### Upload Single Voice
```
POST /upload-voice
Content-Type: multipart/form-data

file: <audio file>
name: "CustomVoice"
```

### Upload Multiple Voices (ZIP)
```
POST /upload-voices-zip
Content-Type: multipart/form-data

file: <zip archive>
cache_immediately: true
```

### Pre-Cache a Voice
```
POST /cache-voice/{voice_name}
```

### Cache All Voices
```
POST /cache-all
```

### Delete a Voice
```
DELETE /voices/{voice_name}
```

### Generate Parameters

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
