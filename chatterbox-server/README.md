# Chatterbox TTS Server Setup

This folder contains configuration for running [devnen/Chatterbox-TTS-Server](https://github.com/devnen/Chatterbox-TTS-Server) as our premium Ultra Voices backend.

## Quick Start (RunPod GPU Pod)

### 1. Create a RunPod Pod
- Template: `RunPod Pytorch 2.1`
- GPU: Any NVIDIA GPU (RTX 3090, A10, etc.) - Recommended: RTX 3090 or A10 for fast generation
- Disk: 50GB+ (for model cache)
- Expose port: **8004**

### 2. SSH into the Pod and run:

```bash
# Clone the server
git clone https://github.com/devnen/Chatterbox-TTS-Server.git
cd Chatterbox-TTS-Server

# Create venv and install
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements-nvidia.txt

# Start server on port 8004
python server.py --port 8004
```

### 3. Set Environment Variable on Railway

```
CHATTERBOX_URL=https://YOUR-POD-ID-8004.proxy.runpod.net
```

## API Endpoints

The devnen server uses these endpoints:

- `POST /tts` - Main TTS endpoint (returns streaming audio)
- `GET /get_predefined_voices` - List available voice files
- `GET /` - Health check

### TTS Request Format

```json
{
  "text": "Hello world",
  "voice_mode": "predefined",
  "predefined_voice_id": "speaker1.wav",
  "exaggeration": 0.5,
  "cfg_weight": 0.5,
  "temperature": 0.8,
  "split_text": true,
  "chunk_size": 200,
  "output_format": "wav"
}
```

### Parameters
- `text`: Text to synthesize
- `voice_mode`: "predefined" (use voice file) or "upload" (send audio)
- `predefined_voice_id`: Filename from ./voices folder
- `exaggeration`: Emotion intensity 0.0-1.0 (default 0.5)
- `cfg_weight`: CFG weight for generation (default 0.5)
- `temperature`: Sampling temperature (default 0.8)
- `split_text`: Auto-chunk long text (default true)
- `chunk_size`: Max chars per chunk (default 200)

## Multi-Speaker Support

Our webapp handles multi-speaker dialogue by:
1. Parsing `[S1]: text [S2]: text` format in user input
2. Making separate API calls per speaker segment with different voice files
3. Concatenating audio chunks with 400ms silence gaps
4. Returning final merged WAV file

### Example Input
```
[S1]: Hello, how are you today?
[S2]: I'm doing great, thanks for asking!
[S1]: That's wonderful to hear.
```

This generates 3 separate TTS calls and merges them.

## Setting Up Predefined Voices

**IMPORTANT:** You must add voice reference files for multi-speaker to work!

### 1. Create the voices folder on the Chatterbox server:
```bash
cd Chatterbox-TTS-Server
mkdir -p voices
```

### 2. Add reference voice files:
```
voices/
  speaker1.wav  - First speaker (e.g., male voice)
  speaker2.wav  - Second speaker (e.g., female voice)
  speaker3.wav  - Third speaker
  speaker4.wav  - Fourth speaker
  ... up to speaker8.wav
```

### Voice File Requirements:
- Format: WAV (16-bit PCM recommended)
- Duration: 5-15 seconds of clear speech
- Quality: Clean recording, minimal background noise
- Content: Natural conversational speech

### Where to Get Voice Samples:
- Record your own samples
- Use royalty-free voice samples
- Extract clips from CC0/public domain audio
- Use AI-generated voice samples (check licensing)

### Mapping in webapp/app.py:
```python
CHATTERBOX_SPEAKER_VOICES = {
    '1': 'speaker1.wav',  # [S1]: maps to this
    '2': 'speaker2.wav',  # [S2]: maps to this
    '3': 'speaker3.wav',  # [S3]: maps to this
    ...
}
```

## Config

Edit `config.yaml` on the server to customize:
- Device (cuda/cpu)
- Default generation parameters
- Chunk size for long text

## Troubleshooting

### "No voice file found"
- Ensure voices/ folder exists
- Check voice filename matches exactly (case-sensitive)
- Verify WAV file is valid

### Slow generation
- Use GPU (cuda), not CPU
- Reduce chunk_size for faster streaming
- RTX 3090 generates ~10s audio in ~2-3s

### Out of memory
- Reduce batch size in config
- Use smaller chunk_size
- Restart server to clear cache

## Keeping the Server Running

Use tmux or screen to keep server running after SSH disconnect:
```bash
# Using tmux
tmux new -s tts
python server.py --port 8004
# Press Ctrl+B, then D to detach

# Reattach later
tmux attach -t tts
```
