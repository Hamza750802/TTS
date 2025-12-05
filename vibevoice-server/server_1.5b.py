"""
Podcast TTS Server (1.5B) for CheapTTS
FastAPI wrapper for long-form multi-speaker TTS with VOICE CLONING support.

This uses VibeVoice-1.5B which supports custom voices from audio samples.
Run this instead of server.py if you want custom voice support.

To switch back to the fast realtime model, just run server.py instead.
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
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterator, Tuple
from contextlib import asynccontextmanager

import numpy as np
import torch
from fastapi import FastAPI, HTTPException, WebSocket, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import scipy.io.wavfile as wavfile

# Directories
VOICES_DIR = Path("voices")
CUSTOM_VOICES_DIR = Path("voices/custom")
OUTPUT_DIR = Path("outputs")
TEMP_DIR = Path("temp")

# Create directories
for d in [VOICES_DIR, CUSTOM_VOICES_DIR, OUTPUT_DIR, TEMP_DIR]:
    d.mkdir(exist_ok=True, parents=True)

# Global model instance
model = None
processor = None
model_loaded = False

# Voice registry: name -> audio file path
voice_registry: Dict[str, str] = {}

# Sample rate for VibeVoice output
SAMPLE_RATE = 24000


class TTSRequest(BaseModel):
    """Request for TTS generation"""
    text: str
    voice: str = "Carter"  # Voice name
    cfg_scale: float = 1.5  # Classifier-free guidance scale
    inference_steps: int = 5  # Diffusion steps


class BatchSegment(BaseModel):
    """A single segment for batch generation"""
    text: str
    voice: str = "Carter"


class BatchRequest(BaseModel):
    """Request for batch multi-segment generation"""
    segments: List[BatchSegment]
    silence_ms: int = 300
    crossfade_ms: int = 30


class VoiceCreateRequest(BaseModel):
    """Request to create a voice from existing audio file"""
    name: str
    audio_path: str  # Path to audio file on server


def load_model():
    """Load VibeVoice 1.5B model"""
    global model, processor, model_loaded
    
    model_path = os.environ.get("MODEL_PATH", "microsoft/VibeVoice-1.5B")
    device = os.environ.get("MODEL_DEVICE", "cuda")
    
    print(f"[VibeVoice 1.5B] Loading model from {model_path}...")
    start = time.time()
    
    try:
        from vibevoice.modular.modeling_vibevoice import (
            VibeVoiceForConditionalGeneration
        )
        from vibevoice.processor.vibevoice_processor import (
            VibeVoiceProcessor
        )
        
        # Load processor
        print(f"[VibeVoice 1.5B] Loading processor...")
        processor = VibeVoiceProcessor.from_pretrained(model_path)
        
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
        
        print(f"[VibeVoice 1.5B] Loading model (dtype={load_dtype}, attn={attn_impl})...")
        
        try:
            model = VibeVoiceForConditionalGeneration.from_pretrained(
                model_path,
                torch_dtype=load_dtype,
                device_map=device_map,
                attn_implementation=attn_impl
            )
        except Exception as e:
            print(f"[VibeVoice 1.5B] Flash attention failed, trying SDPA: {e}")
            model = VibeVoiceForConditionalGeneration.from_pretrained(
                model_path,
                torch_dtype=load_dtype,
                device_map=device_map if device != "mps" else None,
                attn_implementation="sdpa"
            )
            if device == "mps":
                model.to("mps")
        
        model.eval()
        
        # Set inference steps
        if hasattr(model, 'set_ddpm_inference_steps'):
            model.set_ddpm_inference_steps(num_steps=5)
        
        model_loaded = True
        elapsed = time.time() - start
        print(f"[VibeVoice 1.5B] Model loaded in {elapsed:.1f}s")
        
        # Load voice registry
        load_voice_registry()
        
    except Exception as e:
        print(f"[VibeVoice 1.5B] Failed to load model: {e}")
        traceback.print_exc()
        model_loaded = False


def load_voice_registry():
    """Load available voices from custom directory"""
    global voice_registry
    
    voice_registry = {}
    
    # Load built-in voice names (these use different logic in 1.5B)
    builtin_voices = [
        "Carter", "Davis", "Emma", "Frank", "Grace", "Mike", "Samuel"
    ]
    
    # For built-in voices, we don't have audio files, so mark them specially
    for name in builtin_voices:
        voice_registry[name.lower()] = f"builtin:{name}"
    
    # Load custom voices from audio files
    audio_extensions = ['.wav', '.mp3', '.flac', '.ogg', '.m4a']
    
    for audio_file in CUSTOM_VOICES_DIR.glob("*"):
        if audio_file.suffix.lower() in audio_extensions:
            voice_name = audio_file.stem
            voice_registry[voice_name.lower()] = str(audio_file)
            print(f"[VibeVoice 1.5B] Registered custom voice: {voice_name}")
    
    print(f"[VibeVoice 1.5B] Loaded {len(voice_registry)} voices: {list(voice_registry.keys())}")


def get_voice_audio(voice_name: str) -> Optional[str]:
    """Get audio file path for a voice, or None for built-in"""
    name_lower = voice_name.lower()
    
    if name_lower in voice_registry:
        path = voice_registry[name_lower]
        if path.startswith("builtin:"):
            return None  # Built-in voice, no audio file needed
        return path
    
    # Try case-insensitive match
    for key, path in voice_registry.items():
        if key.lower() == name_lower:
            if path.startswith("builtin:"):
                return None
            return path
    
    return None


def generate_audio(text: str, voice: str, cfg_scale: float = 1.5, inference_steps: int = 5) -> bytes:
    """Generate audio from text using voice (can be custom audio file)"""
    global model, processor
    
    if not model_loaded:
        raise RuntimeError("Model not loaded")
    
    device = os.environ.get("MODEL_DEVICE", "cuda")
    
    # Get voice audio if custom
    voice_audio_path = get_voice_audio(voice)
    
    # Format script for the model
    # 1.5B model expects format like "Speaker 0: text"
    script = f"Speaker 0: {text}"
    
    # Process input with optional voice sample
    if voice_audio_path and os.path.exists(voice_audio_path):
        # Custom voice - pass audio sample
        inputs = processor(
            text=script,
            voice_samples=[voice_audio_path],
            padding=True,
            return_tensors="pt",
            return_attention_mask=True,
        )
    else:
        # Built-in voice or no custom audio
        inputs = processor(
            text=script,
            padding=True,
            return_tensors="pt",
            return_attention_mask=True,
        )
    
    # Move tensors to device
    target_device = device if device != "cpu" else "cpu"
    for k, v in inputs.items():
        if torch.is_tensor(v):
            inputs[k] = v.to(target_device)
    
    # Generate
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=None,
            cfg_scale=cfg_scale,
            tokenizer=processor.tokenizer,
            generation_config={'do_sample': False},
        )
    
    # Extract audio
    if hasattr(outputs, 'speech_outputs') and outputs.speech_outputs:
        audio = outputs.speech_outputs[0]
    elif hasattr(outputs, 'audio'):
        audio = outputs.audio
    else:
        raise RuntimeError("No audio in model output")
    
    # Convert to numpy
    if torch.is_tensor(audio):
        audio = audio.cpu().numpy()
    
    # Ensure correct shape
    if audio.ndim > 1:
        audio = audio.squeeze()
    
    # Normalize to int16
    audio = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio * 32767).astype(np.int16)
    
    # Create WAV bytes
    buffer = io.BytesIO()
    wavfile.write(buffer, SAMPLE_RATE, audio_int16)
    return buffer.getvalue()


def generate_batch(segments: List[BatchSegment], silence_ms: int = 300, crossfade_ms: int = 30) -> bytes:
    """Generate audio for multiple segments and concatenate"""
    
    if not segments:
        raise ValueError("No segments provided")
    
    all_audio = []
    silence_samples = int(SAMPLE_RATE * silence_ms / 1000)
    silence = np.zeros(silence_samples, dtype=np.float32)
    
    for i, seg in enumerate(segments):
        print(f"[VibeVoice 1.5B] Generating segment {i+1}/{len(segments)}: {seg.voice}")
        
        try:
            audio_bytes = generate_audio(seg.text, seg.voice)
            
            # Parse WAV to get samples
            buffer = io.BytesIO(audio_bytes)
            sr, audio_data = wavfile.read(buffer)
            
            # Convert to float
            if audio_data.dtype == np.int16:
                audio_data = audio_data.astype(np.float32) / 32767.0
            
            all_audio.append(audio_data)
            
            # Add silence between segments (except after last)
            if i < len(segments) - 1:
                all_audio.append(silence)
                
        except Exception as e:
            print(f"[VibeVoice 1.5B] Segment {i+1} failed: {e}")
            continue
    
    if not all_audio:
        raise RuntimeError("All segments failed")
    
    # Concatenate
    combined = np.concatenate(all_audio)
    
    # Normalize and convert to int16
    combined = np.clip(combined, -1.0, 1.0)
    combined_int16 = (combined * 32767).astype(np.int16)
    
    # Create WAV
    buffer = io.BytesIO()
    wavfile.write(buffer, SAMPLE_RATE, combined_int16)
    return buffer.getvalue()


# FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup"""
    load_model()
    yield


app = FastAPI(
    title="Podcast TTS Server (1.5B with Voice Cloning)",
    version="2.0.0",
    lifespan=lifespan
)

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
        "model": "VibeVoice-1.5B",
        "model_loaded": model_loaded,
        "voices_count": len(voice_registry),
        "custom_voices": [k for k, v in voice_registry.items() if not v.startswith("builtin:")]
    }


@app.get("/voices")
async def list_voices():
    """List available voices"""
    voices = []
    for name, path in voice_registry.items():
        voices.append({
            "id": name,
            "name": name.title(),
            "type": "builtin" if path.startswith("builtin:") else "custom"
        })
    return {"voices": voices}


@app.post("/voices/upload")
async def upload_voice(
    name: str = Form(...),
    audio: UploadFile = File(...)
):
    """Upload a custom voice audio sample"""
    
    # Validate name
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").lower()
    if not safe_name:
        raise HTTPException(400, "Invalid voice name")
    
    # Check file type
    allowed_types = ['.wav', '.mp3', '.flac', '.ogg', '.m4a']
    suffix = Path(audio.filename).suffix.lower()
    if suffix not in allowed_types:
        raise HTTPException(400, f"Invalid audio format. Allowed: {allowed_types}")
    
    # Save file
    dest_path = CUSTOM_VOICES_DIR / f"{safe_name}{suffix}"
    
    try:
        with open(dest_path, "wb") as f:
            content = await audio.read()
            f.write(content)
        
        # Register voice
        voice_registry[safe_name] = str(dest_path)
        
        return {
            "success": True,
            "voice_id": safe_name,
            "message": f"Voice '{safe_name}' created successfully"
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to save voice: {e}")


@app.delete("/voices/{voice_id}")
async def delete_voice(voice_id: str):
    """Delete a custom voice"""
    
    voice_id_lower = voice_id.lower()
    
    if voice_id_lower not in voice_registry:
        raise HTTPException(404, "Voice not found")
    
    path = voice_registry[voice_id_lower]
    
    if path.startswith("builtin:"):
        raise HTTPException(400, "Cannot delete built-in voices")
    
    try:
        if os.path.exists(path):
            os.remove(path)
        del voice_registry[voice_id_lower]
        return {"success": True, "message": f"Voice '{voice_id}' deleted"}
    except Exception as e:
        raise HTTPException(500, f"Failed to delete voice: {e}")


@app.post("/generate")
async def generate(request: TTSRequest):
    """Generate audio for a single text"""
    
    if not model_loaded:
        raise HTTPException(503, "Model not loaded")
    
    try:
        start = time.time()
        audio_bytes = generate_audio(
            request.text,
            request.voice,
            request.cfg_scale,
            request.inference_steps
        )
        elapsed = time.time() - start
        
        # Save to temp file
        output_file = TEMP_DIR / f"gen_{int(time.time()*1000)}.wav"
        with open(output_file, "wb") as f:
            f.write(audio_bytes)
        
        return FileResponse(
            output_file,
            media_type="audio/wav",
            filename="generated.wav",
            headers={
                "X-Generation-Time": str(elapsed),
                "X-Audio-Duration": str(len(audio_bytes) / SAMPLE_RATE / 2)  # Approx
            }
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Generation failed: {e}")


@app.post("/batch-generate")
async def batch_generate(request: BatchRequest):
    """Generate audio for multiple segments"""
    
    if not model_loaded:
        raise HTTPException(503, "Model not loaded")
    
    try:
        start = time.time()
        audio_bytes = generate_batch(
            request.segments,
            request.silence_ms,
            request.crossfade_ms
        )
        elapsed = time.time() - start
        
        # Save to temp file
        output_file = TEMP_DIR / f"batch_{int(time.time()*1000)}.wav"
        with open(output_file, "wb") as f:
            f.write(audio_bytes)
        
        return FileResponse(
            output_file,
            media_type="audio/wav",
            filename="batch_generated.wav",
            headers={
                "X-Generation-Time": str(elapsed),
                "X-Segments-Count": str(len(request.segments))
            }
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Batch generation failed: {e}")


@app.post("/preview")
async def preview_voice(voice: str, text: str = "Hello! This is a preview of my voice."):
    """Generate a short preview of a voice"""
    
    if not model_loaded:
        raise HTTPException(503, "Model not loaded")
    
    try:
        audio_bytes = generate_audio(text, voice, cfg_scale=1.5, inference_steps=5)
        
        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=preview.wav"}
        )
    except Exception as e:
        raise HTTPException(500, f"Preview failed: {e}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8085))
    print(f"[VibeVoice 1.5B] Starting server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
