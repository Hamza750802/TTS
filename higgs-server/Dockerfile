# HiggsAudio v2 Server with vLLM Backend
# Requires: NVIDIA GPU with 24GB+ VRAM (RTX 4090, A6000, A100, etc.)

FROM nvcr.io/nvidia/pytorch:25.02-py3

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Clone HiggsAudio repository
RUN git clone https://github.com/boson-ai/higgs-audio.git /app/higgs-audio

WORKDIR /app/higgs-audio

# Install HiggsAudio dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install -e .

# Install additional dependencies for our server
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    python-multipart \
    aiofiles

# Copy our custom server
COPY server.py /app/server.py
COPY preload_model.py /app/preload_model.py

WORKDIR /app

# Pre-download the model on build (optional, saves startup time)
# RUN python preload_model.py

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run server
CMD ["python", "server.py"]
