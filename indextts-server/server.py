"""
IndexTTS2 Server for CheapTTS
FastAPI wrapper for IndexTTS2 with pre-cached voice embeddings.

The server extracts and caches voice embeddings on first use,
then reuses them for instant generation.

Runs on Vast.ai GPU instance (RTX 3090/4090, ~6GB VRAM in FP16 mode).
"""

import os
import sys
import io
import json
import time
import uuid
import pickle
import asyncio
import zipfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

import torch
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Directories
VOICES_DIR = Path("voices")
CACHE_DIR = Path("cache")  # For embeddings cache
OUTPUT_DIR = Path("outputs")
TEMP_DIR = Path("temp")

# Create directories
for d in [VOICES_DIR, CACHE_DIR, OUTPUT_DIR, TEMP_DIR]:
    d.mkdir(exist_ok=True)

# Global model instance
tts_model = None
model_loaded = False

# Voice embedding cache - stores extracted embeddings for all voices
# Key: voice_name, Value: dict with spk_cond, style, prompt, etc.
voice_cache: Dict[str, Dict[str, Any]] = {}


class TTSRequest(BaseModel):
    """Request for single-speaker TTS generation"""
    text: str
    voice: str = "Emily"  # Voice name (without extension)
    # Emotion control options
    emo_alpha: float = 0.6  # Emotion intensity (0.0-1.0)
    use_emo_text: bool = False  # Use text content to infer emotion
    emo_text: Optional[str] = None  # Separate emotion description
    emo_vector: Optional[List[float]] = None  # [happy, angry, sad, afraid, disgusted, melancholic, surprised, calm]
    # Generation options
    use_random: bool = False  # Enable stochastic sampling


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
        # Add indextts to path
        indextts_path = Path("index-tts")
        if indextts_path.exists():
            sys.path.insert(0, str(indextts_path))
        
        from indextts.infer_v2 import IndexTTS2
        
        # Determine checkpoint path
        checkpoint_dir = "checkpoints"
        if indextts_path.exists():
            checkpoint_dir = str(indextts_path / "checkpoints")
        
        tts_model = IndexTTS2(
            cfg_path=f"{checkpoint_dir}/config.yaml",
            model_dir=checkpoint_dir,
            use_fp16=True,  # FP16 for lower VRAM (~4-6GB)
            use_cuda_kernel=False,  # Disable for compatibility
            use_deepspeed=False  # Disable for simplicity
        )
        
        model_loaded = True
        print(f"[IndexTTS2] Model loaded in {time.time() - start:.2f}s")
        
        # Pre-cache existing voices
        preload_voice_cache()
        
    except Exception as e:
        print(f"[IndexTTS2] Failed to load model: {e}")
        import traceback
        traceback.print_exc()
        raise


def get_voice_audio_path(voice_name: str) -> Optional[str]:
    """Get the audio path for a voice from the voices directory"""
    for ext in [".wav", ".mp3", ".flac"]:
        voice_path = VOICES_DIR / f"{voice_name}{ext}"
        if voice_path.exists():
            return str(voice_path)
    return None


def extract_voice_embedding(voice_name: str, audio_path: str) -> Dict[str, Any]:
    """
    Extract and cache voice embedding from audio file.
    
    This extracts the same data that IndexTTS2 caches internally,
    but we store it persistently so it survives server restarts.
    """
    global tts_model
    
    if tts_model is None:
        raise RuntimeError("Model not loaded")
    
    print(f"[IndexTTS2] Extracting embedding for '{voice_name}' from {audio_path}...")
    start = time.time()
    
    import torchaudio
    import librosa
    
    # Load and preprocess audio (same as IndexTTS2.infer_generator does)
    audio, sr = librosa.load(audio_path)
    audio = torch.tensor(audio).unsqueeze(0)
    
    # Limit to 15 seconds
    max_audio_samples = int(15 * sr)
    if audio.shape[1] > max_audio_samples:
        audio = audio[:, :max_audio_samples]
    
    # Resample
    audio_22k = torchaudio.transforms.Resample(sr, 22050)(audio)
    audio_16k = torchaudio.transforms.Resample(sr, 16000)(audio)
    
    # Extract features using the model's feature extractor
    inputs = tts_model.extract_features(audio_16k, sampling_rate=16000, return_tensors="pt")
    input_features = inputs["input_features"].to(tts_model.device)
    attention_mask = inputs["attention_mask"].to(tts_model.device)
    
    # Get speaker embedding
    spk_cond_emb = tts_model.get_emb(input_features, attention_mask)
    
    # Get semantic codes
    _, S_ref = tts_model.semantic_codec.quantize(spk_cond_emb)
    
    # Get mel spectrogram
    ref_mel = tts_model.mel_fn(audio_22k.to(spk_cond_emb.device).float())
    ref_target_lengths = torch.LongTensor([ref_mel.size(2)]).to(ref_mel.device)
    
    # Get style from campplus model
    feat = torchaudio.compliance.kaldi.fbank(
        audio_16k.to(ref_mel.device),
        num_mel_bins=80,
        dither=0,
        sample_frequency=16000
    )
    feat = feat - feat.mean(dim=0, keepdim=True)
    style = tts_model.campplus_model(feat.unsqueeze(0))
    
    # Get prompt condition
    prompt_condition = tts_model.s2mel.models['length_regulator'](
        S_ref,
        ylens=ref_target_lengths,
        n_quantizers=3,
        f0=None
    )[0]
    
    # Store the cached data
    embedding_data = {
        "name": voice_name,
        "audio_path": audio_path,
        "spk_cond_emb": spk_cond_emb.cpu(),
        "style": style.cpu(),
        "prompt_condition": prompt_condition.cpu(),
        "ref_mel": ref_mel.cpu(),
        "extracted_at": time.time()
    }
    
    # Save to disk cache
    cache_path = CACHE_DIR / f"{voice_name}.pkl"
    with open(cache_path, "wb") as f:
        pickle.dump(embedding_data, f)
    
    print(f"[IndexTTS2] Extracted embedding for '{voice_name}' in {time.time() - start:.2f}s")
    
    return embedding_data


def load_voice_from_cache(voice_name: str) -> Optional[Dict[str, Any]]:
    """Load a voice embedding from disk cache"""
    cache_path = CACHE_DIR / f"{voice_name}.pkl"
    if cache_path.exists():
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            print(f"[IndexTTS2] Failed to load cache for {voice_name}: {e}")
    return None


def preload_voice_cache():
    """Load all cached voice embeddings into memory"""
    global voice_cache
    
    print("[IndexTTS2] Preloading voice cache...")
    
    # Load from disk cache
    for cache_file in CACHE_DIR.glob("*.pkl"):
        voice_name = cache_file.stem
        try:
            data = load_voice_from_cache(voice_name)
            if data:
                voice_cache[voice_name] = data
                print(f"  - Loaded cached embedding: {voice_name}")
        except Exception as e:
            print(f"  - Failed to load {voice_name}: {e}")
    
    print(f"[IndexTTS2] Loaded {len(voice_cache)} cached voices")
    
    # Check for new voice files that need extraction
    for ext in ["*.wav", "*.mp3", "*.flac"]:
        for voice_file in VOICES_DIR.glob(ext):
            voice_name = voice_file.stem
            if voice_name not in voice_cache:
                print(f"  - New voice found: {voice_name} (will extract on first use)")


def get_or_extract_embedding(voice_name: str) -> Dict[str, Any]:
    """Get voice embedding from cache, or extract it if not cached"""
    global voice_cache
    
    # Check memory cache first
    if voice_name in voice_cache:
        return voice_cache[voice_name]
    
    # Check disk cache
    cached = load_voice_from_cache(voice_name)
    if cached:
        voice_cache[voice_name] = cached
        return cached
    
    # Need to extract from audio file
    audio_path = get_voice_audio_path(voice_name)
    if not audio_path:
        raise FileNotFoundError(f"Voice '{voice_name}' not found. Add {voice_name}.wav to voices/ directory.")
    
    # Extract and cache
    embedding = extract_voice_embedding(voice_name, audio_path)
    voice_cache[voice_name] = embedding
    
    return embedding


def generate_speech_with_cache(
    text: str,
    voice: str,
    emo_alpha: float = 0.6,
    use_emo_text: bool = False,
    emo_text: Optional[str] = None,
    emo_vector: Optional[List[float]] = None,
    use_random: bool = False
) -> bytes:
    """
    Generate speech using cached voice embedding for instant generation.
    """
    global tts_model
    
    if not model_loaded or tts_model is None:
        raise RuntimeError("Model not loaded")
    
    # Get cached embedding
    embedding = get_or_extract_embedding(voice)
    
    print(f"[IndexTTS2] Generating with cached voice '{voice}': text_len={len(text)}")
    start = time.time()
    
    # Set the model's internal cache to our cached values
    # This tricks the model into using our pre-extracted embedding
    tts_model.cache_spk_cond = embedding["spk_cond_emb"].to(tts_model.device)
    tts_model.cache_s2mel_style = embedding["style"].to(tts_model.device)
    tts_model.cache_s2mel_prompt = embedding["prompt_condition"].to(tts_model.device)
    tts_model.cache_spk_audio_prompt = embedding["audio_path"]
    tts_model.cache_mel = embedding["ref_mel"].to(tts_model.device)
    
    # Also set emotion cache to same voice (for consistent emotion reference)
    tts_model.cache_emo_cond = embedding["spk_cond_emb"].to(tts_model.device)
    tts_model.cache_emo_audio_prompt = embedding["audio_path"]
    
    # Generate unique output filename
    output_filename = f"gen_{uuid.uuid4().hex[:8]}.wav"
    output_path = OUTPUT_DIR / output_filename
    
    # Build inference kwargs
    kwargs = {
        "spk_audio_prompt": embedding["audio_path"],  # Needed for cache check
        "text": text,
        "output_path": str(output_path),
        "verbose": False
    }
    
    # Add emotion control
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
    print(f"[IndexTTS2] Generated in {gen_time:.2f}s (using cached embedding)")
    
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
    """List all available voices"""
    voices = []
    seen = set()
    
    # Check voices directory
    for ext in ["*.wav", "*.mp3", "*.flac"]:
        for f in VOICES_DIR.glob(ext):
            name = f.stem
            if name not in seen:
                seen.add(name)
                is_cached = name in voice_cache or (CACHE_DIR / f"{name}.pkl").exists()
                voices.append({
                    "id": name,
                    "name": name,
                    "cached": is_cached,
                    "status": "ready" if is_cached else "will_cache_on_first_use"
                })
    
    return sorted(voices, key=lambda x: x["name"])


# FastAPI app with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup"""
    load_model()
    yield
    print("[IndexTTS2] Shutting down...")


app = FastAPI(
    title="IndexTTS2 Server",
    description="High-quality zero-shot TTS with emotion control and cached voice embeddings",
    version="2.0.0",
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
        "cached_voices": len(voice_cache),
        "total_voices": len(list_available_voices())
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy" if model_loaded else "loading",
        "model_loaded": model_loaded,
        "cached_voices": len(voice_cache)
    }


@app.get("/voices")
async def get_voices():
    """List available voices"""
    voices = list_available_voices()
    return {
        "success": True,
        "voices": voices,
        "count": len(voices),
        "cached_count": sum(1 for v in voices if v.get("cached"))
    }


@app.post("/cache-voice/{voice_name}")
async def cache_voice(voice_name: str, background_tasks: BackgroundTasks):
    """
    Pre-cache a voice embedding.
    Call this after uploading a voice file to extract the embedding immediately.
    """
    if not model_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    
    audio_path = get_voice_audio_path(voice_name)
    if not audio_path:
        raise HTTPException(status_code=404, detail=f"Voice file not found: {voice_name}")
    
    if voice_name in voice_cache:
        return {"success": True, "message": f"Voice '{voice_name}' already cached"}
    
    try:
        embedding = extract_voice_embedding(voice_name, audio_path)
        voice_cache[voice_name] = embedding
        return {
            "success": True,
            "message": f"Voice '{voice_name}' cached successfully",
            "voice_id": voice_name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cache-all")
async def cache_all_voices():
    """Cache all voice files that aren't already cached"""
    if not model_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    
    cached = []
    errors = []
    
    for ext in ["*.wav", "*.mp3", "*.flac"]:
        for voice_file in VOICES_DIR.glob(ext):
            voice_name = voice_file.stem
            if voice_name not in voice_cache:
                try:
                    embedding = extract_voice_embedding(voice_name, str(voice_file))
                    voice_cache[voice_name] = embedding
                    cached.append(voice_name)
                    
                    # Clear CUDA cache after each extraction to prevent OOM
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        
                except Exception as e:
                    errors.append({"voice": voice_name, "error": str(e)})
                    # Try to recover from OOM errors
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
    
    return {
        "success": True,
        "cached": cached,
        "errors": errors,
        "total_cached": len(voice_cache)
    }


@app.post("/generate")
async def generate(request: TTSRequest):
    """Generate speech from text using cached voice embedding"""
    if not model_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")
    
    if len(request.text) > 10000:
        raise HTTPException(status_code=400, detail="Text too long (max 10000 chars)")
    
    try:
        start = time.time()
        
        audio_bytes = generate_speech_with_cache(
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
                "X-Text-Length": str(len(request.text)),
                "X-Voice": request.voice,
                "X-Cached": "true" if request.voice in voice_cache else "false"
            }
        )
        
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"[IndexTTS2] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload-voice")
async def upload_voice(
    file: UploadFile = File(...),
    name: str = Form(...)
):
    """
    Upload a voice reference audio file and cache its embedding.
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
        
        # Extract and cache embedding immediately
        embedding = extract_voice_embedding(voice_name, str(audio_path))
        voice_cache[voice_name] = embedding
        
        return VoiceUploadResponse(
            success=True,
            voice_id=voice_name,
            message=f"Voice '{voice_name}' uploaded and cached. Ready for instant generation!"
        )
        
    except Exception as e:
        print(f"[IndexTTS2] Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/voices/{voice_name}")
async def delete_voice(voice_name: str):
    """Delete a voice (audio file and cached embedding)"""
    deleted = []
    
    # Delete from memory cache
    if voice_name in voice_cache:
        del voice_cache[voice_name]
        deleted.append("memory_cache")
    
    # Delete disk cache
    cache_path = CACHE_DIR / f"{voice_name}.pkl"
    if cache_path.exists():
        cache_path.unlink()
        deleted.append("disk_cache")
    
    # Delete audio files
    for ext in [".wav", ".mp3", ".flac"]:
        audio_path = VOICES_DIR / f"{voice_name}{ext}"
        if audio_path.exists():
            audio_path.unlink()
            deleted.append("audio_file")
    
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Voice '{voice_name}' not found")
    
    return {"success": True, "deleted": deleted}


@app.post("/upload-voices-zip")
async def upload_voices_zip(file: UploadFile = File(...), cache_immediately: bool = Form(True)):
    """
    Upload multiple voice reference files as a ZIP archive.
    Each file in the ZIP will be saved as a separate voice.
    Voice name = filename without extension.
    
    Example: voices.zip containing:
      - emily.wav -> voice "emily"
      - michael.wav -> voice "michael"
    """
    if not model_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    
    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")
    
    uploaded = []
    cached = []
    errors = []
    
    try:
        content = await file.read()
        with zipfile.ZipFile(io.BytesIO(content), 'r') as zf:
            for name in zf.namelist():
                # Skip directories and hidden files
                if name.endswith('/') or name.startswith('__') or name.startswith('.'):
                    continue
                
                # Check if it's an audio file
                lower_name = name.lower()
                if not any(lower_name.endswith(ext) for ext in ['.wav', '.mp3', '.flac']):
                    continue
                
                try:
                    # Extract voice name from filename
                    basename = Path(name).name
                    voice_name = Path(basename).stem
                    voice_name = "".join(c for c in voice_name if c.isalnum() or c in "._-").strip()
                    
                    if not voice_name:
                        continue
                    
                    # Get extension
                    ext = Path(basename).suffix.lower()
                    audio_path = VOICES_DIR / f"{voice_name}{ext}"
                    
                    # Extract and save
                    with zf.open(name) as src, open(audio_path, 'wb') as dst:
                        dst.write(src.read())
                    
                    uploaded.append(voice_name)
                    
                    # Cache immediately if requested
                    if cache_immediately:
                        try:
                            embedding = extract_voice_embedding(voice_name, str(audio_path))
                            voice_cache[voice_name] = embedding
                            cached.append(voice_name)
                        except Exception as e:
                            errors.append({"voice": voice_name, "error": f"Cache failed: {str(e)}"})
                
                except Exception as e:
                    errors.append({"file": name, "error": str(e)})
        
        return {
            "success": True,
            "uploaded": uploaded,
            "cached": cached,
            "errors": errors,
            "message": f"Uploaded {len(uploaded)} voices, cached {len(cached)}"
        }
        
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/voice/{voice_name}/info")
async def get_voice_info(voice_name: str):
    """Get detailed info about a specific voice"""
    # Check if audio file exists
    audio_path = get_voice_audio_path(voice_name)
    
    # Check cache status
    is_cached = voice_name in voice_cache or (CACHE_DIR / f"{voice_name}.pkl").exists()
    
    if not audio_path and not is_cached:
        raise HTTPException(status_code=404, detail=f"Voice '{voice_name}' not found")
    
    info = {
        "name": voice_name,
        "cached": is_cached,
        "audio_file": audio_path
    }
    
    # Get cache metadata if available
    if voice_name in voice_cache:
        cache_data = voice_cache[voice_name]
        info["extracted_at"] = cache_data.get("extracted_at")
    elif (CACHE_DIR / f"{voice_name}.pkl").exists():
        cache_data = load_voice_from_cache(voice_name)
        if cache_data:
            info["extracted_at"] = cache_data.get("extracted_at")
    
    return info


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
