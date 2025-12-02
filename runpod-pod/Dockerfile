# Bark TTS API Server for RunPod Pods
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    flask \
    flask-cors \
    gunicorn \
    scipy \
    numpy

# Install Bark from GitHub
RUN pip install --no-cache-dir git+https://github.com/suno-ai/bark.git

# Bark optimizations - use small models for lower VRAM
ENV SUNO_OFFLOAD_CPU=True
ENV SUNO_USE_SMALL_MODELS=True

# Copy API server
COPY server.py .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD curl -f http://localhost:8000/health || exit 1

# Start server
CMD ["python", "server.py"]
