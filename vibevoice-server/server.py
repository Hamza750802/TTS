"""
Podcast TTS Server for CheapTTS
FastAPI wrapper for long-form multi-speaker TTS.

Runs on Vast.ai GPU instance (RTX 3060 12GB, ~8GB VRAM in BF16).

Features:
- Streaming audio generation with WebSocket
- REST API for non-streaming generation
- Pre-cached voice embeddings for instant generation
- Multi-speaker support with predefined voices
"""

import os
import sys
import io
import json
import time
import copy
import struct
import asyncio
import threading
import traceback
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterator, Tuple
from contextlib import asynccontextmanager

import numpy as np
import torch
from fastapi import FastAPI, HTTPException, WebSocket, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Directories
VOICES_DIR = Path("voices")
OUTPUT_DIR = Path("outputs")
TEMP_DIR = Path("temp")

# Create directories
for d in [VOICES_DIR, OUTPUT_DIR, TEMP_DIR]:
    d.mkdir(exist_ok=True)

# Global model instance
model = None
processor = None
model_loaded = False
voice_cache: Dict[str, Any] = {}

# Sample rate for VibeVoice output
SAMPLE_RATE = 24000


class TTSRequest(BaseModel):
    """Request for TTS generation"""
    text: str
    voice: str = "Wayne"  # Voice name
    cfg_scale: float = 1.5  # Classifier-free guidance scale
    inference_steps: int = 5  # Diffusion steps (default 5 for realtime)


class BatchSegment(BaseModel):
    """A single segment for batch generation"""
    text: str
    voice: str = "Wayne"


class BatchRequest(BaseModel):
    """Request for batch multi-segment generation"""
    segments: List[BatchSegment]
    silence_ms: int = 300
    crossfade_ms: int = 30


def load_model():
    """Load VibeVoice model"""
    global model, processor, model_loaded
    
    model_path = os.environ.get("MODEL_PATH", "microsoft/VibeVoice-Realtime-0.5B")
    device = os.environ.get("MODEL_DEVICE", "cuda")
    
    print(f"[VibeVoice] Loading model from {model_path}...")
    start = time.time()
    
    try:
        from vibevoice.modular.modeling_vibevoice_streaming_inference import (
            VibeVoiceStreamingForConditionalGenerationInference
        )
        from vibevoice.processor.vibevoice_streaming_processor import (
            VibeVoiceStreamingProcessor
        )
        
        # Load processor
        print(f"[VibeVoice] Loading processor...")
        processor = VibeVoiceStreamingProcessor.from_pretrained(model_path)
        
        # Determine dtype and attention implementation
        if device == "cuda":
            load_dtype = torch.bfloat16
            device_map = "cuda"
            attn_impl = "flash_attention_2"
        elif device == "mps":
            load_dtype = torch.float32
            device_map = None
            attn_impl = "sdpa"
        else:
            load_dtype = torch.float32
            device_map = "cpu"
            attn_impl = "sdpa"
        
        print(f"[VibeVoice] Loading model (dtype={load_dtype}, attn={attn_impl})...")
        
        try:
            model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                model_path,
                torch_dtype=load_dtype,
                device_map=device_map,
                attn_implementation=attn_impl
            )
        except Exception as e:
            if attn_impl == "flash_attention_2":
                print(f"[VibeVoice] Flash attention failed, trying SDPA: {e}")
                model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                    model_path,
                    torch_dtype=load_dtype,
                    device_map=device_map,
                    attn_implementation="sdpa"
                )
            else:
                raise e
        
        if device == "mps":
            model.to("mps")
        
        model.eval()
        model.set_ddpm_inference_steps(num_steps=5)
        
        # Configure noise scheduler
        model.model.noise_scheduler = model.model.noise_scheduler.from_config(
            model.model.noise_scheduler.config,
            algorithm_type="sde-dpmsolver++",
            beta_schedule="squaredcos_cap_v2",
        )
        
        # Load voice presets
        load_voice_presets()
        
        model_loaded = True
        print(f"[VibeVoice] Model loaded in {time.time() - start:.2f}s")
        
    except Exception as e:
        print(f"[VibeVoice] Failed to load model: {e}")
        traceback.print_exc()
        raise


def load_voice_presets():
    """Load voice preset files (prefilled prompts)"""
    global voice_cache
    
    # Look for .pt files in voices directory
    presets_dir = VOICES_DIR / "streaming_model"
    if not presets_dir.exists():
        presets_dir = VOICES_DIR
    
    voice_files = list(presets_dir.glob("*.pt"))
    
    if not voice_files:
        print(f"[VibeVoice] No voice presets found in {presets_dir}")
        return
    
    device = os.environ.get("MODEL_DEVICE", "cuda")
    torch_device = torch.device(device if device != "cpu" else "cpu")
    
    for voice_file in voice_files:
        voice_name = voice_file.stem
        try:
            print(f"[VibeVoice] Loading voice preset: {voice_name}")
            prefilled = torch.load(voice_file, map_location=torch_device, weights_only=False)
            voice_cache[voice_name] = prefilled
        except Exception as e:
            print(f"[VibeVoice] Failed to load {voice_name}: {e}")
    
    print(f"[VibeVoice] Loaded {len(voice_cache)} voice presets: {list(voice_cache.keys())}")


def get_voice_preset(voice_name: str) -> Optional[Any]:
    """Get a voice preset by name"""
    if voice_name in voice_cache:
        return voice_cache[voice_name]
    
    # Try case-insensitive match
    for name, preset in voice_cache.items():
        if name.lower() == voice_name.lower():
            return preset
    
    # Return first voice if not found
    if voice_cache:
        first_voice = next(iter(voice_cache.values()))
        print(f"[VibeVoice] Voice '{voice_name}' not found, using default")
        return first_voice
    
    return None


def generate_audio(text: str, voice: str, cfg_scale: float = 1.5, inference_steps: int = 5) -> bytes:
    """Generate audio from text"""
    global model, processor
    
    if not model_loaded:
        raise RuntimeError("Model not loaded")
    
    device = os.environ.get("MODEL_DEVICE", "cuda")
    torch_device = torch.device(device if device != "cpu" else "cpu")
    
    # Get voice preset - MUST deepcopy to avoid corrupting cached preset
    original_preset = get_voice_preset(voice)
    if original_preset is None:
        raise RuntimeError(f"No voice presets available")
    
    # Deep copy the preset so we don't corrupt the cache
    prefilled_outputs = copy.deepcopy(original_preset)
    
    # Clean text
    text = text.strip().replace("'", "'").replace('"', '"').replace('"', '"')
    
    if not text:
        raise ValueError("Empty text")
    
    # Set inference steps
    model.set_ddpm_inference_steps(num_steps=inference_steps)
    
    # Prepare inputs - use a fresh copy of the preset
    inputs = processor.process_input_with_cached_prompt(
        text=text,
        cached_prompt=prefilled_outputs,
        padding=True,
        return_tensors="pt",
        return_attention_mask=True,
    )
    
    # Move to device
    for k, v in inputs.items():
        if torch.is_tensor(v):
            inputs[k] = v.to(torch_device)
    
    print(f"[VibeVoice] Generating: voice={voice}, text_len={len(text)}, cfg={cfg_scale}, steps={inference_steps}")
    start_time = time.time()
    
    # Generate - use another fresh copy for all_prefilled_outputs
    outputs = model.generate(
        **inputs,
        max_new_tokens=None,
        cfg_scale=cfg_scale,
        tokenizer=processor.tokenizer,
        generation_config={'do_sample': False},
        verbose=False,
        all_prefilled_outputs=copy.deepcopy(original_preset),
    )
    
    gen_time = time.time() - start_time
    
    # Get audio
    if outputs.speech_outputs and outputs.speech_outputs[0] is not None:
        audio = outputs.speech_outputs[0]
        
        # Debug: print the shape/type of audio
        if torch.is_tensor(audio):
            print(f"[VibeVoice] Audio tensor shape: {audio.shape}, dtype: {audio.dtype}")
            # Get sample count from last dimension (may be multi-dimensional)
            audio_samples = audio.shape[-1] if len(audio.shape) > 0 else 0
            audio = audio.detach().cpu().to(torch.float32).numpy()
            # Flatten if needed
            if audio.ndim > 1:
                audio = audio.reshape(-1)
        else:
            audio_samples = len(audio) if hasattr(audio, '__len__') else 0
        
        # Check if audio is valid (not empty)
        if audio.size == 0 or audio_samples < 100:
            print(f"[VibeVoice] WARNING: Generated empty/tiny audio ({audio_samples} samples)")
            raise RuntimeError(f"Model generated empty audio for text: {text[:50]}...")
        
        audio_duration = len(audio) / SAMPLE_RATE
        rtf = gen_time / audio_duration if audio_duration > 0 else 0
        print(f"[VibeVoice] Generated {audio_duration:.2f}s audio ({len(audio)} samples) in {gen_time:.2f}s (RTF: {rtf:.2f}x)")
        
        # Convert to WAV
        wav_bytes = numpy_to_wav(audio, SAMPLE_RATE)
        return wav_bytes
    else:
        print(f"[VibeVoice] ERROR: No speech_outputs returned for text: {text[:50]}...")
        raise RuntimeError("No audio generated")


def numpy_to_wav(audio: np.ndarray, sample_rate: int = 24000) -> bytes:
    """Convert numpy audio to WAV bytes"""
    # Normalize to [-1, 1]
    if audio.ndim > 1:
        audio = audio.reshape(-1)
    
    peak = np.max(np.abs(audio))
    if peak > 1.0:
        audio = audio / peak
    
    # Convert to 16-bit PCM
    audio_int16 = (audio * 32767).astype(np.int16)
    
    # Create WAV file
    buffer = io.BytesIO()
    
    # WAV header
    num_samples = len(audio_int16)
    data_size = num_samples * 2  # 16-bit = 2 bytes per sample
    
    buffer.write(b'RIFF')
    buffer.write(struct.pack('<I', 36 + data_size))
    buffer.write(b'WAVE')
    buffer.write(b'fmt ')
    buffer.write(struct.pack('<I', 16))  # fmt chunk size
    buffer.write(struct.pack('<H', 1))   # PCM format
    buffer.write(struct.pack('<H', 1))   # mono
    buffer.write(struct.pack('<I', sample_rate))
    buffer.write(struct.pack('<I', sample_rate * 2))  # byte rate
    buffer.write(struct.pack('<H', 2))   # block align
    buffer.write(struct.pack('<H', 16))  # bits per sample
    buffer.write(b'data')
    buffer.write(struct.pack('<I', data_size))
    buffer.write(audio_int16.tobytes())
    
    return buffer.getvalue()


def concatenate_wav_with_silence(wav_chunks: List[bytes], silence_ms: int = 300) -> bytes:
    """Concatenate multiple WAV files with silence between them"""
    if not wav_chunks:
        return b''
    
    if len(wav_chunks) == 1:
        return wav_chunks[0]
    
    # Parse WAV files and extract audio data
    audio_arrays = []
    sample_rate = None
    
    for wav_bytes in wav_chunks:
        # Skip RIFF header and find data chunk
        buffer = io.BytesIO(wav_bytes)
        buffer.read(4)  # RIFF
        buffer.read(4)  # file size
        buffer.read(4)  # WAVE
        
        while buffer.tell() < len(wav_bytes):
            chunk_id = buffer.read(4)
            chunk_size = struct.unpack('<I', buffer.read(4))[0]
            
            if chunk_id == b'fmt ':
                buffer.read(2)  # format
                buffer.read(2)  # channels
                sample_rate = struct.unpack('<I', buffer.read(4))[0]
                buffer.read(chunk_size - 8)
            elif chunk_id == b'data':
                audio_data = buffer.read(chunk_size)
                audio_int16 = np.frombuffer(audio_data, dtype=np.int16)
                audio_arrays.append(audio_int16)
                break
            else:
                buffer.read(chunk_size)
    
    if not audio_arrays or sample_rate is None:
        return wav_chunks[0]
    
    # Create silence
    silence_samples = int(sample_rate * silence_ms / 1000)
    silence = np.zeros(silence_samples, dtype=np.int16)
    
    # Concatenate with silence
    result = []
    for i, audio in enumerate(audio_arrays):
        result.append(audio)
        if i < len(audio_arrays) - 1:
            result.append(silence)
    
    combined = np.concatenate(result)
    
    # Convert back to WAV
    return numpy_to_wav(combined.astype(np.float32) / 32767, sample_rate)


# ==================== FastAPI App ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup"""
    try:
        load_model()
    except Exception as e:
        print(f"[VibeVoice] Model loading failed: {e}")
        traceback.print_exc()
    yield


app = FastAPI(
    title="VibeVoice TTS Server",
    description="VibeVoice-Realtime-0.5B TTS API for CheapTTS",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy" if model_loaded else "loading",
        "model_loaded": model_loaded,
        "voices_loaded": len(voice_cache)
    }


@app.get("/voices")
async def list_voices():
    """List available voices"""
    return {
        "voices": list(voice_cache.keys()),
        "count": len(voice_cache),
        "default": next(iter(voice_cache.keys())) if voice_cache else None
    }


@app.post("/generate")
async def generate(request: TTSRequest):
    """Generate audio from text"""
    try:
        if not model_loaded:
            raise HTTPException(status_code=503, detail="Model not loaded")
        
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Text is required")
        
        start_time = time.time()
        
        audio_bytes = generate_audio(
            text=request.text,
            voice=request.voice,
            cfg_scale=request.cfg_scale,
            inference_steps=request.inference_steps
        )
        
        gen_time = time.time() - start_time
        audio_duration = len(audio_bytes) / (SAMPLE_RATE * 2)  # 16-bit
        
        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/wav",
            headers={
                "X-Generation-Time": str(round(gen_time, 2)),
                "X-Audio-Duration": str(round(audio_duration, 2)),
                "X-Voice": request.voice
            }
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[VibeVoice] Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/batch-generate")
async def batch_generate(request: BatchRequest):
    """Generate audio for multiple segments with different voices"""
    try:
        if not model_loaded:
            raise HTTPException(status_code=503, detail="Model not loaded")
        
        if not request.segments:
            raise HTTPException(status_code=400, detail="No segments provided")
        
        start_time = time.time()
        audio_chunks = []
        
        for i, segment in enumerate(request.segments):
            if not segment.text.strip():
                continue
            
            print(f"[VibeVoice] Batch segment {i+1}/{len(request.segments)}: voice={segment.voice}")
            
            audio_bytes = generate_audio(
                text=segment.text,
                voice=segment.voice,
                cfg_scale=1.5,
                inference_steps=5
            )
            audio_chunks.append(audio_bytes)
        
        if not audio_chunks:
            raise HTTPException(status_code=400, detail="No valid segments")
        
        # Concatenate with silence
        final_audio = concatenate_wav_with_silence(audio_chunks, request.silence_ms)
        
        gen_time = time.time() - start_time
        audio_duration = len(final_audio) / (SAMPLE_RATE * 2)
        
        return StreamingResponse(
            io.BytesIO(final_audio),
            media_type="audio/wav",
            headers={
                "X-Generation-Time": str(round(gen_time, 2)),
                "X-Audio-Duration": str(round(audio_duration, 2)),
                "X-Segments": str(len(audio_chunks))
            }
        )
        
    except Exception as e:
        print(f"[VibeVoice] Batch error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/preview/{voice}")
async def preview_voice(voice: str):
    """Generate a short preview of a voice"""
    try:
        if not model_loaded:
            raise HTTPException(status_code=503, detail="Model not loaded")
        
        preview_text = "Hello! This is a preview of my voice. How does it sound?"
        
        audio_bytes = generate_audio(
            text=preview_text,
            voice=voice,
            cfg_scale=1.5,
            inference_steps=5
        )
        
        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/wav",
            headers={"X-Voice": voice}
        )
        
    except Exception as e:
        print(f"[VibeVoice] Preview error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8085))
    
    print(f"[VibeVoice] Starting server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
