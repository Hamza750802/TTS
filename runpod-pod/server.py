"""
Bark TTS API Server for RunPod Pods
Flask-based REST API with multi-speaker support
Optimized for quality and stability - v2.0
"""

import os
import base64
import io
import re
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np
from scipy.io.wavfile import write as write_wav

print("Loading Bark models (full quality)... (this may take a few minutes on first run)")
from bark import SAMPLE_RATE, generate_audio
from bark.generation import (
    generate_text_semantic,
    preload_models,
)
from bark.api import semantic_to_waveform

# Get semantic rate from generation module
try:
    from bark.generation import SEMANTIC_RATE_HZ
except ImportError:
    SEMANTIC_RATE_HZ = 49.9  # Default value

# Preload all models
preload_models()
print("Models loaded successfully!")

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("BARK_API_KEY", "")

# Speaker voice mapping - most stable voices
SPEAKER_VOICES = {
    "0": "v2/en_speaker_6",   # Female, natural (most stable)
    "1": "v2/en_speaker_0",   # Male, deep
    "2": "v2/en_speaker_6",   # Female, natural
    "3": "v2/en_speaker_1",   # Male, warm
    "4": "v2/en_speaker_9",   # Female, young
    "5": "v2/en_speaker_2",   # Male, clear
    "6": "v2/en_speaker_5",   # Female, soft
    "7": "v2/en_speaker_3",   # Male, energetic
    "8": "v2/en_speaker_7",   # Female, bright
    "narrator": "v2/en_speaker_0",
    "man": "v2/en_speaker_1",
    "woman": "v2/en_speaker_6",
}


def verify_api_key():
    if not API_KEY:
        return True
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:] == API_KEY
    return request.headers.get("X-API-Key") == API_KEY


def clean_text(text):
    """Clean text for optimal Bark generation."""
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    text = re.sub(r'\.{2,}', '.', text)  # Remove ellipsis
    
    # Ensure ends with punctuation
    if text and text[-1] not in '.!?':
        text += '.'
    
    return text


def parse_speakers(text):
    """Parse [S0]: [S1]: etc tags."""
    pattern = r'\[S(\d+)\]:\s*'
    parts = re.split(pattern, text, flags=re.IGNORECASE)
    
    if len(parts) == 1:
        return [(None, text.strip())]
    
    segments = []
    if parts[0].strip():
        segments.append((None, parts[0].strip()))
    
    for i in range(1, len(parts), 2):
        speaker_id = parts[i]
        if i + 1 < len(parts):
            segment_text = parts[i + 1].strip()
            if segment_text:
                voice = SPEAKER_VOICES.get(speaker_id, "v2/en_speaker_6")
                segments.append((voice, segment_text))
    
    return segments


def split_chunks(text, max_chars=150):
    """Split into smaller chunks for better quality. Bark works best with shorter text."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks = []
    current = ""
    
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        
        if len(sent) > max_chars:
            # Split long sentences by commas
            parts = re.split(r'(?<=[,;])\s+', sent)
            for part in parts:
                if len(current) + len(part) + 1 <= max_chars:
                    current = (current + " " + part).strip()
                else:
                    if current:
                        chunks.append(current)
                    current = part
        elif len(current) + len(sent) + 1 <= max_chars:
            current = (current + " " + sent).strip()
        else:
            if current:
                chunks.append(current)
            current = sent
    
    if current:
        chunks.append(current)
    
    # Ensure punctuation
    return [c + '.' if c and c[-1] not in '.!?' else c for c in chunks] if chunks else [text]


def generate_audio_v2(text, voice, temp=0.6):
    """
    Generate audio with strict stopping to prevent hallucination.
    
    Key settings:
    - min_eos_p=0.01: Very aggressive stopping (default 0.2)
    - temp=0.6: Lower temperature for consistency
    - Token limiting based on text length
    """
    # Generate semantic tokens with very strict stopping
    semantic_tokens = generate_text_semantic(
        text,
        history_prompt=voice,
        temp=temp,
        min_eos_p=0.01,  # Stop immediately when model thinks it's done
    )
    
    # Limit tokens based on expected length (prevents long hallucinations)
    # ~15 chars per second, ~50 semantic tokens per second
    expected_duration = len(text) / 15
    max_tokens = int(expected_duration * SEMANTIC_RATE_HZ * 1.3)  # 30% buffer
    
    if len(semantic_tokens) > max_tokens and max_tokens > 30:
        print(f"  Trimming tokens: {len(semantic_tokens)} -> {max_tokens}")
        semantic_tokens = semantic_tokens[:max_tokens]
    
    # Convert to audio
    audio = semantic_to_waveform(semantic_tokens, history_prompt=voice)
    
    # Trim end
    audio = trim_end(audio)
    
    return audio


def trim_end(audio, threshold=0.015):
    """Trim silence and artifacts from end."""
    if len(audio) < SAMPLE_RATE:  # Less than 1 second
        return audio
    
    # Find last significant audio
    abs_audio = np.abs(audio)
    window = 800  # ~33ms
    end_idx = len(audio)
    
    for i in range(len(audio) - window, window, -window):
        if np.max(abs_audio[i:i+window]) > threshold:
            end_idx = i + window
            break
    
    # Safety trim to cut trailing artifacts
    safety_trim = int(SAMPLE_RATE * 0.12)  # 120ms
    end_idx = max(int(SAMPLE_RATE * 0.25), end_idx - safety_trim)
    
    return audio[:end_idx]


def make_silence(ms=70):
    """Generate silence."""
    return np.zeros(int(SAMPLE_RATE * ms / 1000), dtype=np.float32)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "model": "bark", "version": "2.0"})


@app.route("/api/tts", methods=["POST"])
def tts():
    """Generate speech from text."""
    if not verify_api_key():
        return jsonify({"error": "Invalid API key"}), 401
    
    try:
        data = request.get_json() or {}
        text = (data.get("text", "") or "").strip()
        default_voice = data.get("voice", "v2/en_speaker_6")
        temp = min(0.9, max(0.4, float(data.get("temperature", 0.6))))
        
        if not text:
            return jsonify({"error": "No text provided"}), 400
        
        if len(text) > 50000:
            return jsonify({"error": "Text too long (max 50000 chars)"}), 400
        
        start = time.time()
        
        # Check for multi-speaker
        has_speakers = bool(re.search(r'\[S\d+\]:', text, re.IGNORECASE))
        
        segments_audio = []
        chunk_count = 0
        
        if has_speakers:
            segments = parse_speakers(text)
            for idx, (voice, seg_text) in enumerate(segments):
                voice = voice or default_voice
                seg_text = clean_text(seg_text)
                if not seg_text:
                    continue
                
                chunks = split_chunks(seg_text)
                for chunk in chunks:
                    print(f"[{idx+1}/{len(segments)}] {chunk[:35]}...")
                    audio = generate_audio_v2(chunk, voice, temp)
                    
                    if segments_audio:
                        segments_audio.append(make_silence(70))
                    segments_audio.append(audio)
                    chunk_count += 1
        else:
            text = clean_text(text)
            chunks = split_chunks(text)
            for i, chunk in enumerate(chunks):
                print(f"[{i+1}/{len(chunks)}] {chunk[:35]}...")
                audio = generate_audio_v2(chunk, default_voice, temp)
                
                if segments_audio:
                    segments_audio.append(make_silence(50))
                segments_audio.append(audio)
                chunk_count += 1
        
        if not segments_audio:
            return jsonify({"error": "No audio generated"}), 500
        
        # Combine
        full_audio = np.concatenate(segments_audio)
        
        # Normalize
        peak = np.max(np.abs(full_audio))
        if peak > 0:
            full_audio = full_audio / peak * 0.92
        
        # Export WAV
        buf = io.BytesIO()
        write_wav(buf, SAMPLE_RATE, (full_audio * 32767).astype(np.int16))
        buf.seek(0)
        
        duration = len(full_audio) / SAMPLE_RATE
        gen_time = time.time() - start
        
        print(f"✓ {duration:.1f}s audio in {gen_time:.1f}s ({chunk_count} chunks)")
        
        return jsonify({
            "success": True,
            "audio_base64": base64.b64encode(buf.getvalue()).decode(),
            "sample_rate": SAMPLE_RATE,
            "stats": {
                "chunks": chunk_count,
                "duration_sec": round(duration, 2),
                "gen_time_sec": round(gen_time, 2),
                "chars": len(text)
            }
        })
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/voices", methods=["GET"])
def voices():
    return jsonify({"voices": [
        {"id": "v2/en_speaker_6", "name": "Female Natural ⭐", "lang": "en"},
        {"id": "v2/en_speaker_0", "name": "Male Deep", "lang": "en"},
        {"id": "v2/en_speaker_1", "name": "Male Warm", "lang": "en"},
        {"id": "v2/en_speaker_2", "name": "Male Clear", "lang": "en"},
        {"id": "v2/en_speaker_3", "name": "Male Energetic", "lang": "en"},
        {"id": "v2/en_speaker_5", "name": "Female Soft", "lang": "en"},
        {"id": "v2/en_speaker_7", "name": "Female Bright", "lang": "en"},
        {"id": "v2/en_speaker_9", "name": "Female Young", "lang": "en"},
    ]})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Bark TTS API v2.0 on port {port}")
    print("Settings: min_eos_p=0.01, temp=0.6, chunk=150chars")
    app.run(host="0.0.0.0", port=port, threaded=False, debug=False)
