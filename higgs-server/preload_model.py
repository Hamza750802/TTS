"""
Pre-download HiggsAudio models to avoid first-request delay.
Run this during Docker build or before starting the server.
"""

import torch
from huggingface_hub import snapshot_download

MODEL_PATH = "bosonai/higgs-audio-v2-generation-3B-base"
TOKENIZER_PATH = "bosonai/higgs-audio-v2-tokenizer"

print(f"Downloading model: {MODEL_PATH}")
snapshot_download(MODEL_PATH)

print(f"Downloading tokenizer: {TOKENIZER_PATH}")
snapshot_download(TOKENIZER_PATH)

print("Done! Models are cached and ready.")
