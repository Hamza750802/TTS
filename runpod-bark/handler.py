"""
Bark TTS RunPod Serverless Handler
Long-form audio generation with multi-speaker support
"""

import runpod
import os
import base64
import io
import re
import numpy as np
from scipy.io.wavfile import write as write_wav

# Use network volume for model cache if available (faster cold starts)
CACHE_DIR = "/runpod-volume/bark_cache" if os.path.exists("/runpod-volume") else None
if CACHE_DIR:
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.environ["XDG_CACHE_HOME"] = CACHE_DIR
    print(f"Using network volume for model cache: {CACHE_DIR}")
else:
    print("No network volume found, using container storage")

# Enable optimizations for lower VRAM usage
os.environ["SUNO_OFFLOAD_CPU"] = "True"

from bark import SAMPLE_RATE, generate_audio, preload_models
from bark.generation import SAMPLE_RATE, preload_models, generate_text_semantic, semantic_to_waveform

# Pre-load models at startup (not per-request)
print("Loading Bark models...")
preload_models()
print("Models loaded successfully!")

# Speaker voice mapping - maps speaker names/numbers to voice presets
SPEAKER_VOICES = {
    # Numbered speakers
    "1": "v2/en_speaker_0",   # Male, deep
    "2": "v2/en_speaker_6",   # Female, natural
    "3": "v2/en_speaker_3",   # Male, energetic
    "4": "v2/en_speaker_9",   # Female, young
    "5": "v2/en_speaker_1",   # Male, warm
    "6": "v2/en_speaker_5",   # Female, soft
    "7": "v2/en_speaker_2",   # Male, clear
    "8": "v2/en_speaker_7",   # Female, bright
    # Named speakers (common names)
    "narrator": "v2/en_speaker_0",
    "man": "v2/en_speaker_1",
    "woman": "v2/en_speaker_6",
    "boy": "v2/en_speaker_3",
    "girl": "v2/en_speaker_9",
    "host": "v2/en_speaker_0",
    "guest": "v2/en_speaker_6",
}


def parse_multi_speaker_text(text):
    """
    Parse text with speaker tags like [S1]: or [Speaker1]: or [Narrator]:
    Returns list of (speaker_voice, text) tuples
    """
    # Pattern matches [S1], [S2], [Speaker1], [Narrator], etc.
    pattern = r'\[(?:S|Speaker)?(\w+)\]:\s*'
    
    # Split by speaker tags
    parts = re.split(pattern, text, flags=re.IGNORECASE)
    
    # If no speaker tags found, return original text with default voice
    if len(parts) == 1:
        return [(None, text.strip())]
    
    segments = []
    # parts[0] is text before first tag (usually empty)
    # Then alternating: speaker_id, text, speaker_id, text, ...
    
    if parts[0].strip():
        # Text before any speaker tag - use default voice
        segments.append((None, parts[0].strip()))
    
    for i in range(1, len(parts), 2):
        speaker_id = parts[i].lower()
        if i + 1 < len(parts):
            segment_text = parts[i + 1].strip()
            if segment_text:
                # Map speaker to voice
                voice = SPEAKER_VOICES.get(speaker_id)
                if not voice:
                    # Try to use speaker number directly
                    voice = f"v2/en_speaker_{hash(speaker_id) % 10}"
                segments.append((voice, segment_text))
    
    return segments


def split_text_into_chunks(text, max_chars=200):
    """
    Split text into chunks suitable for Bark's ~13 second limit.
    Tries to split on sentence boundaries for natural speech.
    """
    # Split on sentence endings
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        # If single sentence is too long, split on commas/semicolons
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
    
    return chunks


def generate_silence(duration_ms=200):
    """Generate silence padding between chunks"""
    num_samples = int(SAMPLE_RATE * duration_ms / 1000)
    return np.zeros(num_samples, dtype=np.float32)


def generate_long_audio(text, voice_preset="v2/en_speaker_6", silence_padding_ms=200):
    """
    Generate long-form audio by chunking text and using semantic continuation
    for consistent voice across chunks.
    """
    chunks = split_text_into_chunks(text, max_chars=200)
    
    if len(chunks) == 0:
        return None, {"error": "No text provided"}
    
    audio_segments = []
    silence = generate_silence(silence_padding_ms)
    
    # Generate first chunk with voice preset
    print(f"Generating chunk 1/{len(chunks)}: {chunks[0][:50]}...")
    
    # For the first chunk, use the voice preset
    first_audio = generate_audio(chunks[0], history_prompt=voice_preset)
    audio_segments.append(first_audio)
    
    # Generate subsequent chunks
    # Note: For best consistency, we use the same voice preset for all chunks
    # Bark's voice presets are designed to maintain consistency
    for i, chunk in enumerate(chunks[1:], start=2):
        print(f"Generating chunk {i}/{len(chunks)}: {chunk[:50]}...")
        
        # Add silence between chunks
        audio_segments.append(silence)
        
        # Generate with same voice preset for consistency
        chunk_audio = generate_audio(chunk, history_prompt=voice_preset)
        audio_segments.append(chunk_audio)
    
    # Concatenate all audio segments
    full_audio = np.concatenate(audio_segments)
    
    return full_audio, {
        "chunks_generated": len(chunks),
        "total_samples": len(full_audio),
        "duration_seconds": len(full_audio) / SAMPLE_RATE
    }


def generate_multi_speaker_audio(text, default_voice="v2/en_speaker_6", silence_padding_ms=300):
    """
    Generate audio with multiple speakers.
    Parses [S1]:, [S2]:, [Speaker1]:, [Narrator]: etc. tags
    """
    segments = parse_multi_speaker_text(text)
    
    if not segments:
        return None, {"error": "No text provided"}
    
    audio_segments = []
    silence = generate_silence(silence_padding_ms)
    total_chunks = 0
    
    for idx, (voice, segment_text) in enumerate(segments):
        voice = voice or default_voice
        print(f"Generating segment {idx + 1}/{len(segments)} with voice {voice}: {segment_text[:50]}...")
        
        # Split segment into chunks if needed
        chunks = split_text_into_chunks(segment_text, max_chars=200)
        
        for chunk_idx, chunk in enumerate(chunks):
            if audio_segments:  # Add silence between segments
                audio_segments.append(silence)
            
            print(f"  Chunk {chunk_idx + 1}/{len(chunks)}: {chunk[:40]}...")
            chunk_audio = generate_audio(chunk, history_prompt=voice)
            audio_segments.append(chunk_audio)
            total_chunks += 1
    
    if not audio_segments:
        return None, {"error": "No audio generated"}
    
    # Concatenate all audio segments
    full_audio = np.concatenate(audio_segments)
    
    return full_audio, {
        "speakers": len(segments),
        "chunks_generated": total_chunks,
        "total_samples": len(full_audio),
        "duration_seconds": len(full_audio) / SAMPLE_RATE
    }


def handler(job):
    """
    RunPod serverless handler for Bark TTS
    
    Input:
        text: str - The text to convert to speech
                   Supports multi-speaker: [S1]: Hello! [S2]: Hi there!
        voice: str - Default voice preset (e.g., "v2/en_speaker_6")
        silence_padding_ms: int - Silence between chunks (default: 200)
    
    Output:
        audio_base64: str - Base64 encoded WAV audio
        sample_rate: int - Audio sample rate
        stats: dict - Generation statistics
    """
    try:
        job_input = job.get("input", {})
        
        # Extract parameters
        text = job_input.get("text", "")
        voice = job_input.get("voice", "v2/en_speaker_6")
        silence_padding_ms = job_input.get("silence_padding_ms", 200)
        
        # Validate input
        if not text or not text.strip():
            return {"error": "No text provided"}
        
        text = text.strip()
        
        # Check text length (sanity limit)
        if len(text) > 50000:  # ~67 minutes max
            return {"error": "Text too long. Maximum 50,000 characters."}
        
        print(f"Generating audio for {len(text)} characters")
        
        # Check if multi-speaker format
        has_speaker_tags = bool(re.search(r'\[(?:S|Speaker)?\w+\]:', text, re.IGNORECASE))
        
        if has_speaker_tags:
            print("Detected multi-speaker format")
            audio_array, stats = generate_multi_speaker_audio(
                text=text,
                default_voice=voice,
                silence_padding_ms=silence_padding_ms
            )
        else:
            print(f"Single speaker with voice {voice}")
            audio_array, stats = generate_long_audio(
                text=text,
                voice_preset=voice,
                silence_padding_ms=silence_padding_ms
            )
        
        if audio_array is None:
            return stats  # Contains error
        
        # Convert to WAV bytes
        buffer = io.BytesIO()
        
        # Normalize audio to int16 range for WAV
        audio_normalized = np.clip(audio_array, -1.0, 1.0)
        audio_int16 = (audio_normalized * 32767).astype(np.int16)
        
        write_wav(buffer, SAMPLE_RATE, audio_int16)
        buffer.seek(0)
        
        # Encode to base64
        audio_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        print(f"Generation complete: {stats['duration_seconds']:.1f} seconds of audio")
        
        return {
            "audio_base64": audio_base64,
            "sample_rate": SAMPLE_RATE,
            "stats": stats
        }
        
    except Exception as e:
        print(f"Error during generation: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


# Start the serverless worker
runpod.serverless.start({"handler": handler})
