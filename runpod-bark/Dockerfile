# Bark TTS RunPod Worker
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Bark from GitHub
RUN pip install --no-cache-dir git+https://github.com/suno-ai/bark.git

# Copy handler
COPY handler.py .

# Models will download on first request (avoids build timeout)
# First request takes ~2-3 min, subsequent requests are fast

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV SUNO_OFFLOAD_CPU=True

# Run the handler
CMD ["python", "-u", "handler.py"]
