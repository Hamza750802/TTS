# Bark TTS RunPod Worker

Serverless GPU worker for generating premium AI voice audio using Bark TTS.

## Features

- Long-form audio generation (unlimited length via chunking)
- 100+ voice presets across 13 languages
- Natural emotion and special sounds ([laughter], [sighs], ♪ music ♪)
- Optimized for low VRAM usage with CPU offloading

## Voice Presets

### English
- `v2/en_speaker_0` through `v2/en_speaker_9` (10 voices)

### Other Languages
- German: `v2/de_speaker_0` - `v2/de_speaker_9`
- Spanish: `v2/es_speaker_0` - `v2/es_speaker_9`
- French: `v2/fr_speaker_0` - `v2/fr_speaker_9`
- Hindi: `v2/hi_speaker_0` - `v2/hi_speaker_9`
- Italian: `v2/it_speaker_0` - `v2/it_speaker_9`
- Japanese: `v2/ja_speaker_0` - `v2/ja_speaker_9`
- Korean: `v2/ko_speaker_0` - `v2/ko_speaker_9`
- Polish: `v2/pl_speaker_0` - `v2/pl_speaker_9`
- Portuguese: `v2/pt_speaker_0` - `v2/pt_speaker_9`
- Russian: `v2/ru_speaker_0` - `v2/ru_speaker_9`
- Turkish: `v2/tr_speaker_0` - `v2/tr_speaker_9`
- Chinese: `v2/zh_speaker_0` - `v2/zh_speaker_9`

## Special Effects

Include these in your text for special sounds:
- `[laughter]` or `[laughs]` - Laughter
- `[sighs]` - Sighing
- `[gasps]` - Gasping
- `[clears throat]` - Throat clearing
- `[music]` - Background music
- `♪` - Wrap lyrics in music notes for singing
- `...` or `—` - Hesitations/pauses
- `CAPS` - Emphasis on words
- `[MAN]` or `[WOMAN]` - Bias toward male/female voice

## API Input

```json
{
    "input": {
        "text": "Hello! [laughs] This is a test.",
        "voice": "v2/en_speaker_6",
        "silence_padding_ms": 200
    }
}
```

## API Output

```json
{
    "audio_base64": "<base64 encoded WAV>",
    "sample_rate": 24000,
    "stats": {
        "chunks_generated": 3,
        "total_samples": 720000,
        "duration_seconds": 30.0
    }
}
```

## Build & Deploy

### Build Docker Image
```bash
docker build -t your-dockerhub/bark-tts-worker:latest .
docker push your-dockerhub/bark-tts-worker:latest
```

### Deploy to RunPod
1. Go to RunPod Serverless
2. Create new endpoint
3. Use image: `your-dockerhub/bark-tts-worker:latest`
4. Select GPU: A10G (recommended) or RTX 3090
5. Set idle timeout: 5 seconds
6. Deploy

## Local Testing

```bash
python handler.py --test_input '{"input": {"text": "Hello world", "voice": "v2/en_speaker_6"}}'
```

Or with test file:
```bash
python handler.py
```
(Uses test_input.json automatically)
