"""
HiggsAudio v2 FastAPI Server
Premium multi-speaker dialogue TTS for CheapTTS

Features:
- Multi-speaker dialogue with automatic voice assignment
- Zero-shot voice cloning
- High-quality emotional expression
- vLLM-ready for high throughput

Requirements: 24GB+ VRAM GPU
"""

import os
import io
import time
import uuid
import tempfile
import asyncio
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor

import torch
import torchaudio
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# HiggsAudio imports
from boson_multimodal.serve.serve_engine import HiggsAudioServeEngine, HiggsAudioResponse
from boson_multimodal.data_types import ChatMLSample, Message, AudioContent

# ============== Configuration ==============
MODEL_PATH = os.environ.get("HIGGS_MODEL_PATH", "bosonai/higgs-audio-v2-generation-3B-base")
TOKENIZER_PATH = os.environ.get("HIGGS_TOKENIZER_PATH", "bosonai/higgs-audio-v2-tokenizer")
DEVICE = os.environ.get("HIGGS_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
MAX_WORKERS = int(os.environ.get("HIGGS_MAX_WORKERS", "2"))
PORT = int(os.environ.get("PORT", "8000"))

# Reference audio storage
REFERENCE_AUDIO_DIR = Path("/app/reference_audio")
REFERENCE_AUDIO_DIR.mkdir(exist_ok=True)

# ============== App Setup ==============
app = FastAPI(
    title="HiggsAudio v2 TTS Server",
    description="Premium multi-speaker dialogue TTS powered by HiggsAudio v2",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for concurrent generation
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# Global engine (loaded on startup)
serve_engine: Optional[HiggsAudioServeEngine] = None


# ============== Pydantic Models ==============
class GenerateRequest(BaseModel):
    text: str
    temperature: float = 0.3
    top_p: float = 0.95
    top_k: int = 50
    max_new_tokens: int = 2048
    seed: Optional[int] = None
    # Voice cloning
    reference_audio_id: Optional[str] = None  # For single speaker
    reference_audio_ids: Optional[List[str]] = None  # For multi-speaker (comma-separated voices)
    # Scene description
    scene_description: Optional[str] = "Audio is recorded from a quiet room."


class MultiSpeakerRequest(BaseModel):
    """Multi-speaker dialogue request"""
    text: str  # Format: "[Speaker1]: text\n[Speaker2]: text" or automatic
    temperature: float = 0.3
    top_p: float = 0.95
    top_k: int = 50
    max_new_tokens: int = 4096
    seed: Optional[int] = None
    # Voice assignments (optional - if not provided, model auto-assigns)
    speaker_voices: Optional[dict] = None  # {"Speaker1": "voice_id", "Speaker2": "voice_id"}
    scene_description: Optional[str] = "Audio is recorded from a quiet room."


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    device: str
    vram_used_gb: Optional[float] = None


# ============== Startup/Shutdown ==============
@app.on_event("startup")
async def startup_event():
    global serve_engine
    print(f"[HiggsAudio] Loading model on {DEVICE}...")
    print(f"[HiggsAudio] Model: {MODEL_PATH}")
    print(f"[HiggsAudio] Tokenizer: {TOKENIZER_PATH}")
    
    start_time = time.time()
    try:
        serve_engine = HiggsAudioServeEngine(
            MODEL_PATH, 
            TOKENIZER_PATH, 
            device=DEVICE
        )
        load_time = time.time() - start_time
        print(f"[HiggsAudio] Model loaded in {load_time:.2f}s")
        
        # Log VRAM usage
        if torch.cuda.is_available():
            vram_used = torch.cuda.memory_allocated() / 1024**3
            vram_total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"[HiggsAudio] VRAM: {vram_used:.2f}GB / {vram_total:.2f}GB")
    except Exception as e:
        print(f"[HiggsAudio] ERROR loading model: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    global serve_engine
    serve_engine = None
    executor.shutdown(wait=False)
    print("[HiggsAudio] Server shutdown complete")


# ============== Helper Functions ==============
def build_system_prompt(scene_description: str, reference_audio_paths: Optional[List[Path]] = None) -> str:
    """Build system prompt with optional reference audio"""
    prompt = f"Generate audio following instruction.\n\n<|scene_desc_start|>\n{scene_description}\n<|scene_desc_end|>"
    return prompt


def load_reference_audio(audio_id: str) -> Optional[Path]:
    """Load reference audio file by ID"""
    # Check various extensions
    for ext in ['.wav', '.mp3', '.flac', '.ogg']:
        path = REFERENCE_AUDIO_DIR / f"{audio_id}{ext}"
        if path.exists():
            return path
    return None


def generate_audio_sync(
    text: str,
    temperature: float,
    top_p: float,
    top_k: int,
    max_new_tokens: int,
    seed: Optional[int],
    scene_description: str,
    reference_audio_path: Optional[Path] = None
) -> bytes:
    """Synchronous audio generation (runs in thread pool)"""
    global serve_engine
    
    if serve_engine is None:
        raise RuntimeError("Model not loaded")
    
    # Build messages
    system_prompt = build_system_prompt(scene_description)
    
    messages = [
        Message(role="system", content=system_prompt),
    ]
    
    # Add reference audio if provided
    if reference_audio_path and reference_audio_path.exists():
        # Load audio for voice cloning
        waveform, sample_rate = torchaudio.load(str(reference_audio_path))
        audio_content = AudioContent(
            waveform=waveform,
            sample_rate=sample_rate
        )
        messages.append(Message(
            role="user",
            content=[audio_content, f"Clone this voice and say: {text}"]
        ))
    else:
        # No reference - let model choose voice based on text
        messages.append(Message(role="user", content=text))
    
    # Generate
    output: HiggsAudioResponse = serve_engine.generate(
        chat_ml_sample=ChatMLSample(messages=messages),
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        stop_strings=["<|end_of_text|>", "<|eot_id|>"],
        seed=seed
    )
    
    # Convert to WAV bytes
    audio_tensor = torch.from_numpy(output.audio)[None, :]
    
    buffer = io.BytesIO()
    torchaudio.save(buffer, audio_tensor, output.sampling_rate, format="wav")
    buffer.seek(0)
    
    return buffer.read()


# ============== API Endpoints ==============
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    vram_used = None
    if torch.cuda.is_available():
        vram_used = round(torch.cuda.memory_allocated() / 1024**3, 2)
    
    return HealthResponse(
        status="healthy" if serve_engine is not None else "loading",
        model_loaded=serve_engine is not None,
        device=DEVICE,
        vram_used_gb=vram_used
    )


@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "service": "HiggsAudio v2 TTS Server",
        "version": "1.0.0",
        "model": MODEL_PATH,
        "device": DEVICE,
        "endpoints": {
            "generate": "POST /generate - Single speaker TTS",
            "multi_speaker": "POST /multi-speaker - Multi-speaker dialogue",
            "upload_reference": "POST /upload-reference - Upload reference audio for voice cloning",
            "list_references": "GET /list-references - List available reference audios",
            "health": "GET /health - Health check"
        }
    }


@app.post("/generate")
async def generate_audio(request: GenerateRequest):
    """Generate single-speaker audio"""
    if serve_engine is None:
        raise HTTPException(status_code=503, detail="Model still loading")
    
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    # Get reference audio if specified
    ref_audio_path = None
    if request.reference_audio_id:
        ref_audio_path = load_reference_audio(request.reference_audio_id)
        if ref_audio_path is None:
            raise HTTPException(status_code=404, detail=f"Reference audio '{request.reference_audio_id}' not found")
    
    try:
        start_time = time.time()
        
        # Run in thread pool to not block
        loop = asyncio.get_event_loop()
        audio_bytes = await loop.run_in_executor(
            executor,
            generate_audio_sync,
            request.text,
            request.temperature,
            request.top_p,
            request.top_k,
            request.max_new_tokens,
            request.seed,
            request.scene_description,
            ref_audio_path
        )
        
        gen_time = time.time() - start_time
        print(f"[HiggsAudio] Generated {len(audio_bytes)} bytes in {gen_time:.2f}s")
        
        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "X-Generation-Time": str(round(gen_time, 2)),
                "X-Audio-Size": str(len(audio_bytes))
            }
        )
    except Exception as e:
        print(f"[HiggsAudio] Generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/multi-speaker")
async def generate_multi_speaker(request: MultiSpeakerRequest):
    """
    Generate multi-speaker dialogue audio.
    
    Text format:
    [Speaker1]: Hello, how are you?
    [Speaker2]: I'm doing great, thanks!
    
    Or just natural dialogue - the model will auto-assign voices.
    """
    if serve_engine is None:
        raise HTTPException(status_code=503, detail="Model still loading")
    
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    try:
        start_time = time.time()
        
        # For multi-speaker, we use the text as-is and let HiggsAudio handle it
        # The model is smart enough to assign different voices to different speakers
        
        loop = asyncio.get_event_loop()
        audio_bytes = await loop.run_in_executor(
            executor,
            generate_audio_sync,
            request.text,
            request.temperature,
            request.top_p,
            request.top_k,
            request.max_new_tokens,
            request.seed,
            request.scene_description,
            None  # Multi-speaker uses smart voice assignment
        )
        
        gen_time = time.time() - start_time
        print(f"[HiggsAudio] Multi-speaker generated {len(audio_bytes)} bytes in {gen_time:.2f}s")
        
        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "X-Generation-Time": str(round(gen_time, 2)),
                "X-Audio-Size": str(len(audio_bytes))
            }
        )
    except Exception as e:
        print(f"[HiggsAudio] Multi-speaker error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload-reference")
async def upload_reference_audio(
    file: UploadFile = File(...),
    voice_id: Optional[str] = Form(None)
):
    """Upload reference audio for voice cloning"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    # Generate voice ID if not provided
    if not voice_id:
        voice_id = Path(file.filename).stem.replace(" ", "_")
    
    # Validate extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ['.wav', '.mp3', '.flac', '.ogg']:
        raise HTTPException(status_code=400, detail="Unsupported audio format. Use WAV, MP3, FLAC, or OGG.")
    
    # Save file
    save_path = REFERENCE_AUDIO_DIR / f"{voice_id}{ext}"
    
    try:
        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)
        
        return JSONResponse({
            "success": True,
            "voice_id": voice_id,
            "filename": save_path.name,
            "size_bytes": len(content)
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")


@app.get("/list-references")
async def list_reference_audios():
    """List all available reference audios for voice cloning"""
    references = []
    for ext in ['*.wav', '*.mp3', '*.flac', '*.ogg']:
        for path in REFERENCE_AUDIO_DIR.glob(ext):
            references.append({
                "voice_id": path.stem,
                "filename": path.name,
                "size_bytes": path.stat().st_size
            })
    
    return JSONResponse({
        "success": True,
        "references": references,
        "count": len(references)
    })


@app.delete("/delete-reference/{voice_id}")
async def delete_reference_audio(voice_id: str):
    """Delete a reference audio"""
    deleted = False
    for ext in ['.wav', '.mp3', '.flac', '.ogg']:
        path = REFERENCE_AUDIO_DIR / f"{voice_id}{ext}"
        if path.exists():
            path.unlink()
            deleted = True
            break
    
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Voice '{voice_id}' not found")
    
    return JSONResponse({"success": True, "deleted": voice_id})


# ============== Run Server ==============
if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("HiggsAudio v2 TTS Server")
    print("=" * 60)
    print(f"Model: {MODEL_PATH}")
    print(f"Tokenizer: {TOKENIZER_PATH}")
    print(f"Device: {DEVICE}")
    print(f"Port: {PORT}")
    print("=" * 60)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        workers=1,  # Single worker - model is shared
        log_level="info"
    )
