# VibeVoice Server - Voice Cloning Edition (1.5B)

This is the 1.5B model server with **custom voice cloning** support.

## Quick Start

### Switch to 1.5B (Voice Cloning)
```bash
# Stop the current server first
pkill -f "python server.py"

# Run the 1.5B server instead
python server_1.5b.py
```

### Switch Back to 0.5B (Fast Realtime)
```bash
# Stop the 1.5B server
pkill -f "python server_1.5b.py"

# Run the original fast server
python server.py
```

## Adding Custom Voices

### Option 1: Upload via API
```bash
curl -X POST "http://localhost:8085/voices/upload" \
  -F "name=MyVoice" \
  -F "audio=@/path/to/voice_sample.wav"
```

### Option 2: Copy files directly
Just copy WAV/MP3 files to `voices/custom/`:
```bash
cp my_voice.wav voices/custom/
# The voice will be available as "my_voice"
```

## Voice Sample Guidelines

- **Duration**: 10-30 seconds of clean speech
- **Quality**: Clear, minimal background noise
- **Format**: WAV preferred (16-bit, 24kHz or 44.1kHz)
- **Content**: Natural speech, not singing or shouting

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server health + voice list |
| `/voices` | GET | List all voices |
| `/voices/upload` | POST | Upload custom voice |
| `/voices/{id}` | DELETE | Delete custom voice |
| `/generate` | POST | Generate single audio |
| `/batch-generate` | POST | Generate multi-segment |
| `/preview` | POST | Quick voice preview |

## Performance Notes

- 1.5B is ~2-3x slower than 0.5B Realtime
- First generation may be slow (model warmup)
- Custom voices add ~1-2s to first use (encoding)

## Rollback

To go back to the fast 7-voice server:
```bash
python server.py  # Original 0.5B realtime server
```

Your custom voice files in `voices/custom/` are preserved.
