"""
Bark TTS API Server for RunPod Pods
Simple, reliable version using standard Bark API
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

print("Loading Bark models...")
from bark import SAMPLE_RATE, generate_audio
from bark.generation import preload_models

preload_models()
print("Models loaded successfully!")

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("BARK_API_KEY", "")

# Speaker voices
VOICES = {
    "0": "v2/en_speaker_6",
    "1": "v2/en_speaker_0", 
    "2": "v2/en_speaker_1",
    "3": "v2/en_speaker_3",
    "4": "v2/en_speaker_9",
    "5": "v2/en_speaker_2",
    "6": "v2/en_speaker_5",
    "7": "v2/en_speaker_7",
}


def verify_api_key():
    if not API_KEY:
        return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:] == API_KEY
    return request.headers.get("X-API-Key") == API_KEY


def parse_speakers(text):
    """Parse [S0]: [S1]: tags"""
    pattern = r'\[S(\d+)\]:\s*'
    parts = re.split(pattern, text, flags=re.IGNORECASE)
    
    if len(parts) == 1:
        return [(None, text.strip())]
    
    segments = []
    if parts[0].strip():
        segments.append((None, parts[0].strip()))
    
    for i in range(1, len(parts), 2):
        speaker = parts[i]
        if i + 1 < len(parts):
            seg = parts[i + 1].strip()
            if seg:
                voice = VOICES.get(speaker, "v2/en_speaker_6")
                segments.append((voice, seg))
    
    return segments


def make_silence(ms=150):
    """Generate silence between segments"""
    return np.zeros(int(SAMPLE_RATE * ms / 1000), dtype=np.float32)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "model": "bark"})


@app.route("/api/tts", methods=["POST"])
def tts():
    """Generate speech - simple and reliable"""
    if not verify_api_key():
        return jsonify({"error": "Invalid API key"}), 401
    
    try:
        data = request.get_json() or {}
        text = (data.get("text", "") or "").strip()
        default_voice = data.get("voice", "v2/en_speaker_6")
        
        if not text:
            return jsonify({"error": "No text provided"}), 400
        
        if len(text) > 50000:
            return jsonify({"error": "Text too long"}), 400
        
        start = time.time()
        
        # Check for multi-speaker
        has_speakers = bool(re.search(r'\[S\d+\]:', text, re.IGNORECASE))
        
        audio_parts = []
        
        if has_speakers:
            segments = parse_speakers(text)
            for idx, (voice, seg_text) in enumerate(segments):
                voice = voice or default_voice
                print(f"[{idx+1}/{len(segments)}] Generating: {seg_text[:40]}...")
                
                # Use standard Bark generate_audio - most reliable
                audio = generate_audio(seg_text, history_prompt=voice)
                
                if audio_parts:
                    audio_parts.append(make_silence(150))
                audio_parts.append(audio)
        else:
            print(f"Generating: {text[:40]}...")
            audio = generate_audio(text, history_prompt=default_voice)
            audio_parts.append(audio)
        
        # Combine
        full_audio = np.concatenate(audio_parts)
        
        # Normalize
        peak = np.max(np.abs(full_audio))
        if peak > 0:
            full_audio = full_audio / peak * 0.95
        
        # Export WAV
        buf = io.BytesIO()
        write_wav(buf, SAMPLE_RATE, (full_audio * 32767).astype(np.int16))
        buf.seek(0)
        
        duration = len(full_audio) / SAMPLE_RATE
        gen_time = time.time() - start
        
        print(f"Done: {duration:.1f}s audio in {gen_time:.1f}s")
        
        return jsonify({
            "success": True,
            "audio_base64": base64.b64encode(buf.getvalue()).decode(),
            "sample_rate": SAMPLE_RATE,
            "stats": {
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
        {"id": "v2/en_speaker_6", "name": "Female Natural", "lang": "en"},
        {"id": "v2/en_speaker_0", "name": "Male Deep", "lang": "en"},
        {"id": "v2/en_speaker_1", "name": "Male Warm", "lang": "en"},
        {"id": "v2/en_speaker_3", "name": "Male Energetic", "lang": "en"},
        {"id": "v2/en_speaker_9", "name": "Female Young", "lang": "en"},
        {"id": "v2/en_speaker_2", "name": "Male Clear", "lang": "en"},
        {"id": "v2/en_speaker_5", "name": "Female Soft", "lang": "en"},
        {"id": "v2/en_speaker_7", "name": "Female Bright", "lang": "en"},
    ]})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Bark TTS API on port {port}")
    app.run(host="0.0.0.0", port=port, threaded=False, debug=False)
