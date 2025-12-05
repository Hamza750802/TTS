"""
Studio Model TTS Server (1.5B) for CheapTTS
FastAPI wrapper for high-quality TTS with hybrid priority queue system.

Features:
- 22 voices (7 built-in + 15 custom)
- Hybrid queue: priority lane for short texts, standard queue for longer texts
- Auto-chunking for texts >2000 chars
- Estimated wait times and queue position feedback

This uses VibeVoice-1.5B model from hmzh59/vibevoice-models.
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
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterator, Tuple
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
import heapq

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

# ============================================================================
# HYBRID QUEUE SYSTEM
# ============================================================================

class QueuePriority(Enum):
    """Queue priority levels"""
    HIGH = 1      # <500 chars - fast lane
    NORMAL = 2    # 500-2000 chars - standard queue
    LOW = 3       # >2000 chars - chunked, background


@dataclass(order=True)
class QueueItem:
    """Item in the priority queue"""
    priority: int  # Combined priority: user_priority * 10 + text_priority
    timestamp: float = field(compare=False)
    request_id: str = field(compare=False)
    text: str = field(compare=False)
    voice: str = field(compare=False)
    cfg_scale: float = field(compare=False)
    inference_steps: int = field(compare=False)
    future: asyncio.Future = field(compare=False)
    char_count: int = field(compare=False)
    user_priority: int = field(compare=False, default=1)  # 1-10 from webapp


class HybridQueue:
    """
    Hybrid priority queue for TTS requests.
    
    - Priority lane: <500 chars, 2 concurrent
    - Standard lane: 500-2000 chars, 1 concurrent  
    - Auto-chunks texts >2000 chars
    """
    
    # Thresholds
    PRIORITY_THRESHOLD = 500      # Chars for priority lane
    STANDARD_THRESHOLD = 2000     # Chars before chunking
    MAX_QUEUE_SIZE = 20           # Max pending requests
    
    # Concurrency limits
    PRIORITY_CONCURRENT = 2       # Parallel short generations
    STANDARD_CONCURRENT = 1       # Sequential long generations
    
    # Timing estimates (seconds per 100 chars)
    AVG_TIME_PER_100_CHARS = 1.5
    
    def __init__(self):
        self._queue: List[QueueItem] = []
        self._lock = asyncio.Lock()
        self._priority_semaphore = asyncio.Semaphore(self.PRIORITY_CONCURRENT)
        self._standard_semaphore = asyncio.Semaphore(self.STANDARD_CONCURRENT)
        self._processing: Dict[str, QueueItem] = {}
        self._stats = {
            "total_processed": 0,
            "total_chars": 0,
            "avg_generation_time": 3.0,  # Initial estimate
        }
        self._generation_times: List[float] = []
    
    def get_priority(self, char_count: int) -> QueuePriority:
        """Determine priority based on text length"""
        if char_count < self.PRIORITY_THRESHOLD:
            return QueuePriority.HIGH
        elif char_count <= self.STANDARD_THRESHOLD:
            return QueuePriority.NORMAL
        else:
            return QueuePriority.LOW
    
    async def enqueue(self, text: str, voice: str, cfg_scale: float, 
                      inference_steps: int, user_priority: int = 1) -> Tuple[str, int, float]:
        """
        Add request to queue.
        
        Priority is calculated as: user_priority * 10 + text_priority
        - user_priority: 1-10 (from webapp, 1=highest, 10=lowest based on usage)
        - text_priority: 1-3 based on text length
        
        This means a throttled user (priority 10) with short text still waits
        behind a normal user (priority 1) with any length text.
        
        Returns (request_id, position, estimated_wait_seconds)
        """
        async with self._lock:
            if len(self._queue) >= self.MAX_QUEUE_SIZE:
                raise HTTPException(
                    status_code=503,
                    detail="Server busy. Please try again in a few seconds.",
                    headers={"Retry-After": "10"}
                )
            
            char_count = len(text)
            text_priority = self.get_priority(char_count)
            
            # Combined priority: user priority dominates, text priority is tiebreaker
            # user_priority 1 = normal user, 5-10 = throttled unlimited user
            combined_priority = user_priority * 10 + text_priority.value
            
            request_id = str(uuid.uuid4())[:8]
            
            loop = asyncio.get_event_loop()
            future = loop.create_future()
            
            item = QueueItem(
                priority=combined_priority,
                timestamp=time.time(),
                request_id=request_id,
                text=text,
                voice=voice,
                cfg_scale=cfg_scale,
                inference_steps=inference_steps,
                future=future,
                char_count=char_count,
                user_priority=user_priority
            )
            
            heapq.heappush(self._queue, item)
            
            position = self._get_position(request_id)
            eta = self._estimate_wait(position, char_count)
            
            if user_priority > 1:
                print(f"[Queue] Enqueued {request_id}: {char_count} chars, user_priority={user_priority}, combined={combined_priority}")
            
            return request_id, position, eta
    
    def _get_position(self, request_id: str) -> int:
        """Get position in queue (1-indexed)"""
        for i, item in enumerate(sorted(self._queue)):
            if item.request_id == request_id:
                return i + 1
        return len(self._queue)
    
    def _estimate_wait(self, position: int, char_count: int) -> float:
        """Estimate wait time in seconds"""
        # Base wait from queue position
        base_wait = (position - 1) * self._stats["avg_generation_time"]
        
        # Add time for this request
        own_time = (char_count / 100) * self.AVG_TIME_PER_100_CHARS
        
        return base_wait + own_time
    
    async def get_status(self, request_id: str) -> Dict[str, Any]:
        """Get status of a request"""
        async with self._lock:
            # Check if processing
            if request_id in self._processing:
                return {
                    "status": "processing",
                    "position": 0,
                    "eta_seconds": 0
                }
            
            # Check queue
            for i, item in enumerate(sorted(self._queue)):
                if item.request_id == request_id:
                    eta = self._estimate_wait(i + 1, item.char_count)
                    return {
                        "status": "queued",
                        "position": i + 1,
                        "eta_seconds": round(eta, 1)
                    }
            
            return {"status": "not_found"}
    
    async def process_next(self):
        """Process next item in queue"""
        async with self._lock:
            if not self._queue:
                return None
            
            item = heapq.heappop(self._queue)
            self._processing[item.request_id] = item
        
        try:
            priority = QueuePriority(item.priority)
            semaphore = (self._priority_semaphore 
                        if priority == QueuePriority.HIGH 
                        else self._standard_semaphore)
            
            async with semaphore:
                start_time = time.time()
                
                # Run generation in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    generate_audio_sync,
                    item.text,
                    item.voice,
                    item.cfg_scale,
                    item.inference_steps
                )
                
                elapsed = time.time() - start_time
                
                # Update stats
                self._generation_times.append(elapsed)
                if len(self._generation_times) > 50:
                    self._generation_times.pop(0)
                self._stats["avg_generation_time"] = sum(self._generation_times) / len(self._generation_times)
                self._stats["total_processed"] += 1
                self._stats["total_chars"] += item.char_count
                
                item.future.set_result((result, elapsed))
                
        except Exception as e:
            item.future.set_exception(e)
        finally:
            async with self._lock:
                self._processing.pop(item.request_id, None)
    
    async def wait_for_result(self, request_id: str, future: asyncio.Future) -> Tuple[bytes, float]:
        """Wait for generation result"""
        return await future
    
    def get_queue_info(self) -> Dict[str, Any]:
        """Get overall queue status"""
        priority_count = sum(1 for item in self._queue if item.priority == QueuePriority.HIGH.value)
        standard_count = len(self._queue) - priority_count
        
        return {
            "queue_length": len(self._queue),
            "priority_queue": priority_count,
            "standard_queue": standard_count,
            "processing": len(self._processing),
            "stats": self._stats.copy()
        }


# Global queue instance
request_queue = HybridQueue()


async def queue_processor():
    """Background task to process queue"""
    while True:
        try:
            if request_queue._queue:
                await request_queue.process_next()
            else:
                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[Queue] Error processing: {e}")
            await asyncio.sleep(0.5)


class TTSRequest(BaseModel):
    """Request for TTS generation"""
    text: str
    voice: str = "Carter"  # Voice name
    cfg_scale: float = 1.5  # Classifier-free guidance scale
    inference_steps: int = 5  # Diffusion steps
    user_priority: int = 1  # User priority 1-10 (1=highest, passed from webapp)


class BatchSegment(BaseModel):
    """A single segment for batch generation"""
    text: str
    voice: str = "Carter"


class BatchRequest(BaseModel):
    """Request for batch multi-segment generation"""
    segments: List[BatchSegment]
    silence_ms: int = 300
    crossfade_ms: int = 30
    user_priority: int = 1  # User priority 1-10 (passed from webapp)


class QueuedResponse(BaseModel):
    """Response when request is queued"""
    request_id: str
    position: int
    eta_seconds: float
    status: str = "queued"


def load_model():
    """Load VibeVoice 1.5B model"""
    global model, processor, model_loaded
    
    # HuggingFace repo with subfolder
    repo_id = os.environ.get("MODEL_REPO", "hmzh59/vibevoice-models")
    subfolder = os.environ.get("MODEL_SUBFOLDER", "VibeVoice-1.5B")
    device = os.environ.get("MODEL_DEVICE", "cuda")
    
    print(f"[Studio Model] Loading model from {repo_id}/{subfolder}...")
    print(f"[Studio Model] High-quality TTS with 22 voices")
    start = time.time()
    
    try:
        from vibevoice.modular.modeling_vibevoice_inference import (
            VibeVoiceForConditionalGenerationInference
        )
        from vibevoice.processor.vibevoice_processor import (
            VibeVoiceProcessor
        )
        
        # Load processor
        print(f"[Studio Model] Loading processor...")
        processor = VibeVoiceProcessor.from_pretrained(repo_id, subfolder=subfolder)
        
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
        
        print(f"[Studio Model] Loading model (dtype={load_dtype}, attn={attn_impl})...")
        
        try:
            model = VibeVoiceForConditionalGenerationInference.from_pretrained(
                repo_id,
                subfolder=subfolder,
                torch_dtype=load_dtype,
                device_map=device_map,
                    attn_implementation=attn_impl
            )
        except Exception as e:
            print(f"[Studio Model] Flash attention failed, trying SDPA: {e}")
            model = VibeVoiceForConditionalGenerationInference.from_pretrained(
                repo_id,
                subfolder=subfolder,
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
        print(f"[Studio Model] Model loaded in {elapsed:.1f}s")
        
        # Load voice registry
        load_voice_registry()
        
    except Exception as e:
        print(f"[Studio Model] Failed to load model: {e}")
        traceback.print_exc()
        model_loaded = False


def load_voice_registry():
    """Load available voices from directories"""
    global voice_registry
    
    voice_registry = {}
    
    # VV demo voices directory (bundled with VV package)
    vv_demo_dir = Path("/root/VV/demo/voices")
    
    # Load custom voices from audio files - check all directories
    audio_extensions = ['.wav', '.mp3', '.flac', '.ogg', '.m4a']
    voice_dirs = [VOICES_DIR, CUSTOM_VOICES_DIR, vv_demo_dir]
    
    for voice_dir in voice_dirs:
        if voice_dir.exists():
            for audio_file in voice_dir.glob("*"):
                if audio_file.suffix.lower() in audio_extensions and audio_file.is_file():
                    # Extract voice name - handle VV demo format like "en-Carter_man.wav"
                    voice_name = audio_file.stem
                    if voice_name.startswith(("en-", "zh-", "in-")):
                        # VV demo voice: "en-Carter_man" -> "Carter"
                        parts = voice_name.split("-", 1)[1]  # "Carter_man"
                        voice_name = parts.split("_")[0]  # "Carter"
                    
                    # Register voice (don't override existing)
                    if voice_name.lower() not in voice_registry:
                        voice_registry[voice_name.lower()] = str(audio_file)
                        print(f"[Studio Model] Registered voice: {voice_name} -> {audio_file}")
    
    print(f"[Studio Model] Loaded {len(voice_registry)} voices: {list(voice_registry.keys())}")


def get_voice_audio(voice_name: str) -> Optional[str]:
    """Get audio file path for a voice"""
    name_lower = voice_name.lower()
    
    if name_lower in voice_registry:
        return voice_registry[name_lower]
    
    # Try case-insensitive match
    for key, path in voice_registry.items():
        if key.lower() == name_lower:
            return path
    
    return None


def generate_audio(text: str, voice: str, cfg_scale: float = 1.5, inference_steps: int = 5) -> bytes:
    """Generate audio from text using voice cloning"""
    global model, processor
    
    if not model_loaded:
        raise RuntimeError("Model not loaded")
    
    device = os.environ.get("MODEL_DEVICE", "cuda")
    
    # Get voice audio file - required for VV 1.5B
    voice_audio_path = get_voice_audio(voice)
    
    if not voice_audio_path or not os.path.exists(voice_audio_path):
        # Fall back to first available voice
        if voice_registry:
            fallback_voice = list(voice_registry.keys())[0]
            voice_audio_path = voice_registry[fallback_voice]
            print(f"[Studio Model] Voice '{voice}' not found, using '{fallback_voice}'")
        else:
            raise RuntimeError(f"No voice samples available")
    
    # Format script for the model
    # 1.5B model expects format like "Speaker 0: text"
    script = f"Speaker 0: {text}"
    
    # Process input with voice sample (always required for 1.5B)
    inputs = processor(
        text=script,
        voice_samples=[voice_audio_path],
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
            cfg_scale=cfg_scale,
            tokenizer=processor.tokenizer,
        )
    
    # Extract audio
    if hasattr(outputs, 'speech_outputs') and outputs.speech_outputs:
        audio = outputs.speech_outputs[0]
    elif hasattr(outputs, 'audio'):
        audio = outputs.audio
    else:
        raise RuntimeError("No audio in model output")
    
    # Convert to numpy (handle bfloat16)
    if torch.is_tensor(audio):
        audio = audio.float().cpu().numpy()
    
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


def generate_audio_sync(text: str, voice: str, cfg_scale: float = 1.5, 
                        inference_steps: int = 5) -> bytes:
    """Synchronous wrapper for generate_audio (for thread pool)"""
    return generate_audio(text, voice, cfg_scale, inference_steps)


def chunk_text(text: str, max_chars: int = 2000) -> List[str]:
    """Split text into chunks at sentence boundaries"""
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # Split by sentences
    sentences = text.replace("。", ".").replace("！", "!").replace("？", "?")
    sentences = sentences.replace(". ", ".|").replace("! ", "!|").replace("? ", "?|")
    sentences = sentences.split("|")
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_chars:
            current_chunk += sentence + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks if chunks else [text[:max_chars]]


# FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup, start queue processor"""
    load_model()
    
    # Start queue processor background task
    processor_task = asyncio.create_task(queue_processor())
    print("[Studio Model] Queue processor started")
    
    yield
    
    # Cleanup
    processor_task.cancel()


app = FastAPI(
    title="Studio Model TTS Server",
    description="High-quality TTS with hybrid priority queue",
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
    queue_info = request_queue.get_queue_info()
    return {
        "status": "healthy" if model_loaded else "loading",
        "model": "Studio-Model-1.5B",
        "model_loaded": model_loaded,
        "voices_count": len(voice_registry),
        "queue": queue_info
    }


@app.get("/queue/status")
async def queue_status():
    """Get overall queue status"""
    return request_queue.get_queue_info()


@app.get("/queue/status/{request_id}")
async def request_status(request_id: str):
    """Get status of a specific request"""
    return await request_queue.get_status(request_id)


@app.get("/voices")
async def list_voices():
    """List available voices"""
    voices = []
    for name, path in voice_registry.items():
        voice_type = "builtin" if path.startswith("builtin:") else "custom"
        voices.append({
            "id": name,
            "name": name.title(),
            "type": voice_type
        })
    
    # Sort: custom first, then builtin, alphabetically within each
    voices.sort(key=lambda v: (0 if v["type"] == "custom" else 1, v["name"]))
    return {"voices": voices}


@app.post("/generate")
async def generate(request: TTSRequest):
    """Generate audio with queue system"""
    
    if not model_loaded:
        raise HTTPException(503, "Model not loaded")
    
    text = request.text.strip()
    if not text:
        raise HTTPException(400, "Text is required")
    
    char_count = len(text)
    
    # Auto-chunk long texts
    if char_count > HybridQueue.STANDARD_THRESHOLD:
        chunks = chunk_text(text, HybridQueue.STANDARD_THRESHOLD)
        if len(chunks) > 1:
            # Convert to batch request
            segments = [BatchSegment(text=chunk, voice=request.voice) for chunk in chunks]
            batch_req = BatchRequest(segments=segments, silence_ms=200, crossfade_ms=50)
            return await batch_generate(batch_req)
    
    try:
        # Add to queue with user priority
        request_id, position, eta = await request_queue.enqueue(
            text=text,
            voice=request.voice,
            cfg_scale=request.cfg_scale,
            inference_steps=request.inference_steps,
            user_priority=request.user_priority
        )
        
        # Find the future for this request
        future = None
        for item in request_queue._queue:
            if item.request_id == request_id:
                future = item.future
                break
        
        if not future:
            raise HTTPException(500, "Failed to queue request")
        
        # Wait for result with queue position updates
        try:
            audio_bytes, elapsed = await asyncio.wait_for(
                request_queue.wait_for_result(request_id, future),
                timeout=120  # 2 minute timeout
            )
        except asyncio.TimeoutError:
            raise HTTPException(504, "Generation timed out")
        
        # Save to temp file
        output_file = TEMP_DIR / f"gen_{request_id}.wav"
        with open(output_file, "wb") as f:
            f.write(audio_bytes)
        
        return FileResponse(
            output_file,
            media_type="audio/wav",
            filename="generated.wav",
            headers={
                "X-Generation-Time": str(round(elapsed, 2)),
                "X-Request-ID": request_id,
                "X-Char-Count": str(char_count)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Generation failed: {e}")


@app.post("/batch-generate")
async def batch_generate(request: BatchRequest):
    """Generate audio for multiple segments with queue"""
    
    if not model_loaded:
        raise HTTPException(503, "Model not loaded")
    
    if not request.segments:
        raise HTTPException(400, "No segments provided")
    
    try:
        start = time.time()
        
        all_audio = []
        silence_samples = int(SAMPLE_RATE * request.silence_ms / 1000)
        silence = np.zeros(silence_samples, dtype=np.float32)
        
        for i, seg in enumerate(request.segments):
            print(f"[Studio Model] Generating segment {i+1}/{len(request.segments)}: {seg.voice}")
            
            # Generate each segment through queue with user priority
            request_id, position, eta = await request_queue.enqueue(
                text=seg.text,
                voice=seg.voice,
                cfg_scale=1.5,
                inference_steps=5,
                user_priority=request.user_priority
            )
            
            # Find future
            future = None
            for item in request_queue._queue:
                if item.request_id == request_id:
                    future = item.future
                    break
            
            if future:
                audio_bytes, _ = await request_queue.wait_for_result(request_id, future)
                
                # Parse WAV
                buffer = io.BytesIO(audio_bytes)
                sr, audio_data = wavfile.read(buffer)
                
                if audio_data.dtype == np.int16:
                    audio_data = audio_data.astype(np.float32) / 32767.0
                
                all_audio.append(audio_data)
                
                if i < len(request.segments) - 1:
                    all_audio.append(silence)
        
        if not all_audio:
            raise HTTPException(500, "All segments failed")
        
        # Concatenate
        combined = np.concatenate(all_audio)
        combined = np.clip(combined, -1.0, 1.0)
        combined_int16 = (combined * 32767).astype(np.int16)
        
        # Create WAV
        buffer = io.BytesIO()
        wavfile.write(buffer, SAMPLE_RATE, combined_int16)
        audio_bytes = buffer.getvalue()
        
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
                "X-Generation-Time": str(round(elapsed, 2)),
                "X-Segments-Count": str(len(request.segments))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Batch generation failed: {e}")


@app.post("/preview")
async def preview_voice(voice: str, text: str = "Hello! This is a preview of my voice."):
    """Generate a short preview of a voice (bypasses queue for speed)"""
    
    if not model_loaded:
        raise HTTPException(503, "Model not loaded")
    
    # Limit preview text length
    preview_text = text[:200] if len(text) > 200 else text
    
    try:
        start = time.time()
        audio_bytes = generate_audio(preview_text, voice, cfg_scale=1.5, inference_steps=3)
        elapsed = time.time() - start
        
        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/wav",
            headers={
                "Content-Disposition": "inline; filename=preview.wav",
                "X-Generation-Time": str(round(elapsed, 2))
            }
        )
    except Exception as e:
        raise HTTPException(500, f"Preview failed: {e}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8070))
    print(f"[Studio Model] Starting server on port {port}...")
    print(f"[Studio Model] Hybrid queue: priority <{HybridQueue.PRIORITY_THRESHOLD} chars, standard <{HybridQueue.STANDARD_THRESHOLD} chars")
    uvicorn.run(app, host="0.0.0.0", port=port)
