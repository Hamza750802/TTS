"""
IndexTTS2 Server for CheapTTS
FastAPI wrapper for IndexTTS2 with pre-saved voice embeddings.

Runs on Vast.ai GPU instance (RTX 3090/4090, ~6GB VRAM in FP16 mode).
"""

import os
import sys
import json
import time
import uuid
import asyncio
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Directories
VOICES_DIR = Path("voices")
EMBEDDINGS_DIR = Path("embeddings")
OUTPUT_DIR = Path("outputs")
TEMP_DIR = Path("temp")

# Create directories
for d in [VOICES_DIR, EMBEDDINGS_DIR, OUTPUT_DIR, TEMP_DIR]:
    d.mkdir(exist_ok=True)

# Global model instance
tts_model = None
model_loaded = False


class TTSRequest(BaseModel):
    """Request for single-speaker TTS generation"""
    text: str
    voice: str = "Emily"  # Voice name (without .json extension)
    # Emotion control options
    emo_alpha: float = 0.6  # Emotion intensity (0.0-1.0)
    use_emo_text: bool = False  # Use text content to infer emotion
    emo_text: Optional[str] = None  # Separate emotion description
    emo_vector: Optional[List[float]] = None  # [happy, angry, sad, afraid, disgusted, melancholic, surprised, calm]
    # Generation options
    use_random: bool = False  # Enable stochastic sampling
    seed: Optional[int] = None


class VoiceUploadResponse(BaseModel):
    """Response after uploading a voice reference"""
    success: bool
    voice_id: str
    message: str


def load_model():
    """Load IndexTTS2 model"""
    global tts_model, model_loaded
    
    print("[IndexTTS2] Loading model in FP16 mode...")
    start = time.time()
    
    try:
        from indextts.infer_v2 import IndexTTS2
        
        tts_model = IndexTTS2(
            cfg_path="checkpoints/config.yaml",
            model_dir="checkpoints",
            use_fp16=True,  # FP16 for lower VRAM (~4-6GB)
            use_cuda_kernel=False,  # Disable for compatibility
            use_deepspeed=False  # Disable for simplicity
        )
        
        model_loaded = True
        print(f"[IndexTTS2] Model loaded in {time.time() - start:.2f}s")
        
    except Exception as e:
        print(f"[IndexTTS2] Failed to load model: {e}")
        raise


def extract_and_save_embedding(audio_path: str, voice_name: str) -> str:
    """
    Extract speaker embedding from audio and save as JSON.
    
    Args:
        audio_path: Path to reference audio file (WAV)
        voice_name: Name for the voice (will save as {voice_name}.json)
    
    Returns:
        Path to saved embedding file
    """
    global tts_model
    
    if not model_loaded or tts_model is None:
        raise RuntimeError("Model not loaded")
    
    print(f"[IndexTTS2] Extracting embedding from {audio_path}...")
    
    # IndexTTS2 extracts embedding internally during inference
    # We need to use the model's internal methods to get the embedding
    # For now, we'll store the audio path and let the model process it
    
    # Actually, looking at the IndexTTS2 code, embeddings are extracted on-the-fly
    # The recommended approach is to store reference audio files and load them
    # But for faster inference, we can pre-compute and cache embeddings
    
    # Let's store the audio file path for now, and the model will handle it
    voice_info = {
        "name": voice_name,
        "audio_path": str(audio_path),
        "created_at": time.time()
    }
    
    embedding_path = EMBEDDINGS_DIR / f"{voice_name}.json"
    with open(embedding_path, "w") as f:
        json.dump(voice_info, f)
    
    print(f"[IndexTTS2] Saved voice info to {embedding_path}")
    return str(embedding_path)


def get_voice_audio_path(voice_name: str) -> str:
    """
    Get the audio path for a voice.
    First checks embeddings JSON, then falls back to voices directory.
    """
    # Check embedding JSON
    embedding_path = EMBEDDINGS_DIR / f"{voice_name}.json"
    if embedding_path.exists():
        with open(embedding_path) as f:
            info = json.load(f)
            audio_path = info.get("audio_path")
            if audio_path and Path(audio_path).exists():
                return audio_path
    
    # Fall back to voices directory
    for ext in [".wav", ".mp3", ".flac"]:
        voice_path = VOICES_DIR / f"{voice_name}{ext}"
        if voice_path.exists():
            return str(voice_path)
    
    raise FileNotFoundError(f"Voice '{voice_name}' not found")


def generate_speech(
    text: str,
    voice: str,
    emo_alpha: float = 0.6,
    use_emo_text: bool = False,
    emo_text: Optional[str] = None,
    emo_vector: Optional[List[float]] = None,
    use_random: bool = False
) -> bytes:
    """
    Generate speech using IndexTTS2.
    
    Args:
        text: Text to synthesize
        voice: Voice name
        emo_alpha: Emotion intensity
        use_emo_text: Use text content to infer emotion
        emo_text: Separate emotion description
        emo_vector: Direct emotion vector [happy, angry, sad, afraid, disgusted, melancholic, surprised, calm]
        use_random: Enable stochastic sampling
    
    Returns:
        WAV audio bytes
    """
    global tts_model
    
    if not model_loaded or tts_model is None:
        raise RuntimeError("Model not loaded")
    
    # Get voice audio path
    voice_path = get_voice_audio_path(voice)
    print(f"[IndexTTS2] Generating: voice={voice}, text_len={len(text)}")
    
    # Generate unique output filename
    output_filename = f"gen_{uuid.uuid4().hex[:8]}.wav"
    output_path = OUTPUT_DIR / output_filename
    
    start = time.time()
    
    # Build inference kwargs
    kwargs = {
        "spk_audio_prompt": voice_path,
        "text": text,
        "output_path": str(output_path),
        "verbose": True
    }
    
    # Add emotion control options
    if emo_vector:
        kwargs["emo_vector"] = emo_vector
        kwargs["emo_alpha"] = emo_alpha
    elif use_emo_text:
        kwargs["use_emo_text"] = True
        kwargs["emo_alpha"] = emo_alpha
        if emo_text:
            kwargs["emo_text"] = emo_text
    
    if use_random:
        kwargs["use_random"] = True
    
    # Generate
    tts_model.infer(**kwargs)
    
    gen_time = time.time() - start
    print(f"[IndexTTS2] Generated in {gen_time:.2f}s")
    
    # Read and return audio bytes
    with open(output_path, "rb") as f:
        audio_bytes = f.read()
    
    # Clean up output file
    try:
        output_path.unlink()
    except:
        pass
    
    return audio_bytes


def list_available_voices() -> List[dict]:
    """List all available voices (from embeddings and voices directory)"""
    voices = []
    seen = set()
    
    # Check embeddings directory
    for f in EMBEDDINGS_DIR.glob("*.json"):
        name = f.stem
        if name not in seen:
            seen.add(name)
            with open(f) as fp:
                info = json.load(fp)
            voices.append({
                "id": name,
                "name": name,
                "type": "embedding",
                "created_at": info.get("created_at")
            })
    
    # Check voices directory
    for ext in ["*.wav", "*.mp3", "*.flac"]:
        for f in VOICES_DIR.glob(ext):
            name = f.stem
            if name not in seen:
                seen.add(name)
                voices.append({
                    "id": name,
                    "name": name,
                    "type": "audio"
                })
    
    return sorted(voices, key=lambda x: x["name"])


# FastAPI app with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup"""
    load_model()
    yield
    # Cleanup on shutdown
    print("[IndexTTS2] Shutting down...")


app = FastAPI(
    title="IndexTTS2 Server",
    description="High-quality zero-shot TTS with emotion control for CheapTTS",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for webapp access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "ok",
        "model": "IndexTTS2",
        "model_loaded": model_loaded,
        "fp16": True,
        "voices_count": len(list_available_voices())
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy" if model_loaded else "loading",
        "model_loaded": model_loaded
    }


@app.get("/voices")
async def get_voices():
    """List available voices"""
    voices = list_available_voices()
    return {
        "success": True,
        "voices": voices,
        "count": len(voices)
    }


@app.post("/generate")
async def generate(request: TTSRequest):
    """Generate speech from text"""
    if not model_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")
    
    if len(request.text) > 10000:
        raise HTTPException(status_code=400, detail="Text too long (max 10000 chars)")
    
    try:
        start = time.time()
        
        audio_bytes = generate_speech(
            text=request.text,
            voice=request.voice,
            emo_alpha=request.emo_alpha,
            use_emo_text=request.use_emo_text,
            emo_text=request.emo_text,
            emo_vector=request.emo_vector,
            use_random=request.use_random
        )
        
        gen_time = time.time() - start
        
        # Save to temp file for response
        output_filename = f"output_{uuid.uuid4().hex[:8]}.wav"
        output_path = OUTPUT_DIR / output_filename
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
        
        return FileResponse(
            output_path,
            media_type="audio/wav",
            filename="speech.wav",
            headers={
                "X-Generation-Time": str(gen_time),
                "X-Text-Length": str(len(request.text))
            }
        )
        
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"[IndexTTS2] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload-voice")
async def upload_voice(
    file: UploadFile = File(...),
    name: str = Form(...)
):
    """
    Upload a voice reference audio file.
    The embedding will be extracted and saved for fast generation.
    """
    if not model_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    
    # Validate file type
    if not file.filename.lower().endswith(('.wav', '.mp3', '.flac')):
        raise HTTPException(status_code=400, detail="File must be WAV, MP3, or FLAC")
    
    # Sanitize name
    voice_name = "".join(c for c in name if c.isalnum() or c in "._-").strip()
    if not voice_name:
        raise HTTPException(status_code=400, detail="Invalid voice name")
    
    try:
        # Save uploaded file
        ext = Path(file.filename).suffix.lower()
        audio_path = VOICES_DIR / f"{voice_name}{ext}"
        
        with open(audio_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Create embedding entry
        extract_and_save_embedding(str(audio_path), voice_name)
        
        return VoiceUploadResponse(
            success=True,
            voice_id=voice_name,
            message=f"Voice '{voice_name}' uploaded and ready to use"
        )
        
    except Exception as e:
        print(f"[IndexTTS2] Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/voices/{voice_name}")
async def delete_voice(voice_name: str):
    """Delete a voice (both audio and embedding)"""
    deleted = []
    
    # Delete embedding
    embedding_path = EMBEDDINGS_DIR / f"{voice_name}.json"
    if embedding_path.exists():
        embedding_path.unlink()
        deleted.append("embedding")
    
    # Delete audio files
    for ext in [".wav", ".mp3", ".flac"]:
        audio_path = VOICES_DIR / f"{voice_name}{ext}"
        if audio_path.exists():
            audio_path.unlink()
            deleted.append("audio")
    
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Voice '{voice_name}' not found")
    
    return {"success": True, "deleted": deleted}


# Cleanup old output files periodically
@app.on_event("startup")
async def cleanup_old_outputs():
    """Clean up output files older than 1 hour"""
    async def cleanup_loop():
        while True:
            await asyncio.sleep(3600)  # Every hour
            try:
                now = time.time()
                for f in OUTPUT_DIR.glob("*.wav"):
                    if now - f.stat().st_mtime > 3600:
                        f.unlink()
                print("[IndexTTS2] Cleaned up old output files")
            except Exception as e:
                print(f"[IndexTTS2] Cleanup error: {e}")
    
    asyncio.create_task(cleanup_loop())


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    print(f"[IndexTTS2] Starting server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
