# Podcast TTS Server for CheapTTS

FastAPI server wrapper for long-form multi-speaker TTS.

## Features

- **Streaming TTS**: Real-time audio generation with ~300ms latency
- **Multi-Speaker**: Support for different voice presets
- **REST API**: Simple HTTP endpoints for integration
- **Long-form**: Supports up to 90 minutes of audio generation

## Requirements

- NVIDIA GPU with 8GB+ VRAM (RTX 3060, 3090, 4090, etc.)
- CUDA 11.8+ / PyTorch 2.0+
- ~10GB disk space for model

## Quick Setup on Vast.ai

1. **Create Instance**:
   - Template: PyTorch 2.x + CUDA
   - GPU: RTX 3060 12GB (minimum) or better
   - Disk: 20GB+
   - Expose port 8080

2. **SSH into instance**:
   ```bash
   ssh -p <port> root@<host> -L 8080:localhost:8080
   ```

3. **Run setup**:
   ```bash
   # Upload or create files
   mkdir -p vibevoice-server && cd vibevoice-server
   # Copy server.py and setup.sh here
   
   # Run setup
   chmod +x setup.sh
   ./setup.sh
   ```

4. **Start server**:
   ```bash
   export MODEL_PATH=microsoft/VibeVoice-Realtime-0.5B
   export MODEL_DEVICE=cuda
   python server.py
   ```

5. **Create tunnel**:
   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```

## API Endpoints

### Health Check
```
GET /health
```

Returns server status and model info.

### List Voices
```
GET /voices
```

Returns available voice presets.

### Generate Audio
```
POST /generate
Content-Type: application/json

{
  "text": "Hello, world!",
  "voice": "Wayne",
  "cfg_scale": 1.5,
  "inference_steps": 5
}
```

Returns WAV audio file.

### Batch Generate (Multi-Speaker)
```
POST /batch-generate
Content-Type: application/json

{
  "segments": [
    {"text": "Hello!", "voice": "Wayne"},
    {"text": "Hi there!", "voice": "Carter"}
  ],
  "silence_ms": 300
}
```

Returns concatenated WAV audio.

### Preview Voice
```
GET /preview/{voice}
```

Returns a short preview of the specified voice.

## Voice Presets

Default voice presets from VibeVoice:
- Wayne
- Carter
- (more available in demo/voices/streaming_model)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| MODEL_PATH | microsoft/VibeVoice-Realtime-0.5B | HuggingFace model path |
| MODEL_DEVICE | cuda | Device (cuda/cpu/mps) |
| PORT | 8080 | Server port |

## Integration with CheapTTS

Set the `VIBEVOICE_URL` environment variable in Railway:
```
VIBEVOICE_URL=https://your-tunnel-url.trycloudflare.com
```

Or use direct Vast.ai port mapping:
```
VIBEVOICE_URL=http://154.17.227.37:30478
```

## Performance

- First token latency: ~300ms
- Real-time factor: ~0.5x (2 seconds of audio per second of generation)
- Supports up to 64K tokens (~90 minutes of audio)
