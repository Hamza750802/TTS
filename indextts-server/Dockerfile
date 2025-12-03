# IndexTTS2 Server Dockerfile for Vast.ai
# Uses NVIDIA PyTorch container with CUDA 12.8+

FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

# Set environment
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    git-lfs \
    ffmpeg \
    libsndfile1 \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager (required by IndexTTS2)
RUN pip install --no-cache-dir uv

# Create app directory
WORKDIR /app

# Clone IndexTTS2
RUN git clone https://github.com/index-tts/index-tts.git /app/indextts && \
    cd /app/indextts && \
    git lfs install && \
    git lfs pull

# Install IndexTTS2 dependencies using uv
WORKDIR /app/indextts
RUN uv sync --extra webui || pip install -e .

# Download model checkpoints
RUN pip install --no-cache-dir "huggingface-hub[cli,hf_xet]" && \
    huggingface-cli download IndexTeam/IndexTTS-2 --local-dir=checkpoints

# Copy our server files
WORKDIR /app
COPY server.py /app/
COPY setup_voices.py /app/

# Create directories
RUN mkdir -p voices embeddings outputs temp

# Install FastAPI dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-multipart \
    pydantic

# Add indextts to Python path
ENV PYTHONPATH="/app/indextts:$PYTHONPATH"

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run server
CMD ["python", "server.py"]
