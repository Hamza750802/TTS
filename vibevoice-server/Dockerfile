FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Clone VibeVoice
RUN git clone --depth 1 https://github.com/microsoft/VibeVoice.git /app/VibeVoice

# Install VibeVoice
WORKDIR /app/VibeVoice
RUN pip install --no-cache-dir -e .

# Install additional dependencies
RUN pip install --no-cache-dir fastapi uvicorn[standard]

# Create directories
WORKDIR /app
RUN mkdir -p voices/streaming_model outputs temp

# Copy server files
COPY server.py .

# Copy voice presets if available
COPY voices/ voices/ 2>/dev/null || true

# Environment variables
ENV MODEL_PATH=microsoft/VibeVoice-Realtime-0.5B
ENV MODEL_DEVICE=cuda
ENV PORT=8080

EXPOSE 8080

CMD ["python", "server.py"]
