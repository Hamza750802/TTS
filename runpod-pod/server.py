"""
Bark TTS API Server for RunPod Pods
Flask-based REST API with multi-speaker support
"""

import os
import base64
import io
import re
import hashlib
import time
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import numpy as np
from scipy.io.wavfile import write as write_wav

# Bark optimizations
os.environ["SUNO_OFFLOAD_CPU"] = "True"
os.environ["SUNO_USE_SMALL_MODELS"] = "True"

print("Loading Bark models... (this may take a few minutes on first run)")
from bark import SAMPLE_RATE, generate_audio, preload_models
preload_models()
print("Models loaded successfully!")

app = Flask(__name__)
CORS(app)

# API Key for security (set via environment variable)
API_KEY = os.environ.get("BARK_API_KEY", "")

# Speaker voice mapping
SPEAKER_VOICES = {
    "1": "v2/en_speaker_0",   # Male, deep
    "2": "v2/en_speaker_6",   # Female, natural
    "3": "v2/en_speaker_3",   # Male, energetic
    "4": "v2/en_speaker_9",   # Female, young
    "5": "v2/en_speaker_1",   # Male, warm
    "6": "v2/en_speaker_5",   # Female, soft
    "7": "v2/en_speaker_2",   # Male, clear
    "8": "v2/en_speaker_7",   # Female, bright
    "narrator": "v2/en_speaker_0",
    "man": "v2/en_speaker_1",
    "woman": "v2/en_speaker_6",
    "boy": "v2/en_speaker_3",
    "girl": "v2/en_speaker_9",
}


def verify_api_key():
    """Verify API key if set"""
    if not API_KEY:
        return True
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:] == API_KEY
    return request.headers.get("X-API-Key") == API_KEY


def parse_multi_speaker_text(text):
    """Parse [S1]: or [Speaker1]: tags"""
    pattern = r'\[(?:S|Speaker)?(\w+)\]:\s*'
    parts = re.split(pattern, text, flags=re.IGNORECASE)
    
    if len(parts) == 1:
        return [(None, text.strip())]
    
    segments = []
    if parts[0].strip():
        segments.append((None, parts[0].strip()))
    
    for i in range(1, len(parts), 2):
        speaker_id = parts[i].lower()
        if i + 1 < len(parts):
            segment_text = parts[i + 1].strip()
            if segment_text:
                voice = SPEAKER_VOICES.get(speaker_id, f"v2/en_speaker_{hash(speaker_id) % 10}")
                segments.append((voice, segment_text))
    
    return segments


def split_text_into_chunks(text, max_chars=200):
    """Split text for Bark's ~13 second limit"""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(sentence) > max_chars:
            sub_parts = re.split(r'(?<=[,;:])\s+', sentence)
            for part in sub_parts:
                if len(current_chunk) + len(part) + 1 <= max_chars:
                    current_chunk = (current_chunk + " " + part).strip()
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = part
        elif len(current_chunk) + len(sentence) + 1 <= max_chars:
            current_chunk = (current_chunk + " " + sentence).strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks if chunks else [text]


def generate_silence(duration_ms=200):
    """Generate silence padding"""
    num_samples = int(SAMPLE_RATE * duration_ms / 1000)
    return np.zeros(num_samples, dtype=np.float32)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "model": "bark"})


@app.route("/api/tts", methods=["POST"])
def text_to_speech():
    """
    Generate speech from text
    
    POST JSON:
        text: str - Text to convert (supports [S1]: multi-speaker format)
        voice: str - Default voice preset (default: v2/en_speaker_6)
        silence_padding_ms: int - Silence between segments (default: 200)
    
    Returns:
        JSON with audio_base64 (WAV) and stats
    """
    if not verify_api_key():
        return jsonify({"error": "Invalid API key"}), 401
    
    try:
        data = request.get_json() or {}
        text = (data.get("text", "") or "").strip()
        default_voice = data.get("voice", "v2/en_speaker_6")
        silence_padding_ms = data.get("silence_padding_ms", 200)
        
        if not text:
            return jsonify({"error": "No text provided"}), 400
        
        if len(text) > 50000:
            return jsonify({"error": "Text too long. Maximum 50,000 characters."}), 400
        
        start_time = time.time()
        
        # Check for multi-speaker format
        has_speaker_tags = bool(re.search(r'\[(?:S|Speaker)?\w+\]:', text, re.IGNORECASE))
        
        audio_segments = []
        silence = generate_silence(silence_padding_ms)
        total_chunks = 0
        
        if has_speaker_tags:
            # Multi-speaker mode
            segments = parse_multi_speaker_text(text)
            for voice, segment_text in segments:
                voice = voice or default_voice
                chunks = split_text_into_chunks(segment_text)
                for chunk in chunks:
                    if audio_segments:
                        audio_segments.append(silence)
                    print(f"Generating: {chunk[:50]}... (voice: {voice})")
                    audio = generate_audio(chunk, history_prompt=voice)
                    audio_segments.append(audio)
                    total_chunks += 1
        else:
            # Single speaker mode
            chunks = split_text_into_chunks(text)
            for chunk in chunks:
                if audio_segments:
                    audio_segments.append(silence)
                print(f"Generating: {chunk[:50]}... (voice: {default_voice})")
                audio = generate_audio(chunk, history_prompt=default_voice)
                audio_segments.append(audio)
                total_chunks += 1
        
        # Concatenate audio
        full_audio = np.concatenate(audio_segments)
        
        # Convert to WAV
        buffer = io.BytesIO()
        audio_normalized = np.clip(full_audio, -1.0, 1.0)
        audio_int16 = (audio_normalized * 32767).astype(np.int16)
        write_wav(buffer, SAMPLE_RATE, audio_int16)
        buffer.seek(0)
        
        audio_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        
        generation_time = time.time() - start_time
        duration_seconds = len(full_audio) / SAMPLE_RATE
        
        print(f"Generated {duration_seconds:.1f}s audio in {generation_time:.1f}s")
        
        return jsonify({
            "success": True,
            "audio_base64": audio_base64,
            "sample_rate": SAMPLE_RATE,
            "stats": {
                "chunks_generated": total_chunks,
                "duration_seconds": duration_seconds,
                "generation_time_seconds": generation_time,
                "characters": len(text)
            }
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/voices", methods=["GET"])
def list_voices():
    """List available voices"""
    voices = [
        {"id": "v2/en_speaker_0", "name": "English Male 1 (Deep)", "language": "en"},
        {"id": "v2/en_speaker_1", "name": "English Male 2 (Warm)", "language": "en"},
        {"id": "v2/en_speaker_2", "name": "English Male 3 (Clear)", "language": "en"},
        {"id": "v2/en_speaker_3", "name": "English Male 4 (Energetic)", "language": "en"},
        {"id": "v2/en_speaker_4", "name": "English Male 5 (Calm)", "language": "en"},
        {"id": "v2/en_speaker_5", "name": "English Female 1 (Soft)", "language": "en"},
        {"id": "v2/en_speaker_6", "name": "English Female 2 (Natural)", "language": "en"},
        {"id": "v2/en_speaker_7", "name": "English Female 3 (Bright)", "language": "en"},
        {"id": "v2/en_speaker_8", "name": "English Female 4 (Mature)", "language": "en"},
        {"id": "v2/en_speaker_9", "name": "English Female 5 (Young)", "language": "en"},
        {"id": "v2/de_speaker_0", "name": "German Speaker 1", "language": "de"},
        {"id": "v2/de_speaker_1", "name": "German Speaker 2", "language": "de"},
        {"id": "v2/es_speaker_0", "name": "Spanish Speaker 1", "language": "es"},
        {"id": "v2/es_speaker_1", "name": "Spanish Speaker 2", "language": "es"},
        {"id": "v2/fr_speaker_0", "name": "French Speaker 1", "language": "fr"},
        {"id": "v2/fr_speaker_1", "name": "French Speaker 2", "language": "fr"},
        {"id": "v2/ja_speaker_0", "name": "Japanese Speaker 1", "language": "ja"},
        {"id": "v2/zh_speaker_0", "name": "Chinese Speaker 1", "language": "zh"},
    ]
    return jsonify({"voices": voices})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Bark TTS API on port {port}")
    
    # Use threaded=False for GPU operations
    app.run(host="0.0.0.0", port=port, threaded=False, debug=False)
