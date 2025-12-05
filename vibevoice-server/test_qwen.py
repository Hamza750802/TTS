#!/usr/bin/env python3
"""Test if Qwen tokenizer can be loaded"""
from transformers import AutoTokenizer

print("Downloading Qwen/Qwen2.5-1.5B tokenizer...")
t = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B")
print("Success! Qwen tokenizer loaded.")
