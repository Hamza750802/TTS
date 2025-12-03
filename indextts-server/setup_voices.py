"""
Setup script to create predefined voices for CheapTTS.
Run this once after deploying the server to create voice embeddings.

This downloads sample voice files and creates embeddings for each.
You can replace these with your own voice samples.
"""

import os
import json
import shutil
from pathlib import Path

# Voice definitions - matches Chatterbox voices
# Each voice needs a reference audio file (5-30 seconds of clear speech)
VOICE_DEFINITIONS = [
    # Primary voices (most used)
    {"name": "Emily", "gender": "female", "style": "warm, friendly narrator"},
    {"name": "Michael", "gender": "male", "style": "professional, clear"},
    {"name": "Olivia", "gender": "female", "style": "expressive, dynamic"},
    {"name": "Ryan", "gender": "male", "style": "casual, conversational"},
    {"name": "Taylor", "gender": "neutral", "style": "modern, neutral"},
    {"name": "Thomas", "gender": "male", "style": "authoritative, deep"},
    
    # Extended voices
    {"name": "Abigail", "gender": "female", "style": "gentle, soothing"},
    {"name": "Adrian", "gender": "male", "style": "energetic, upbeat"},
    {"name": "Alexander", "gender": "male", "style": "sophisticated, British"},
    {"name": "Alice", "gender": "female", "style": "young, cheerful"},
    {"name": "Austin", "gender": "male", "style": "southern, warm"},
    {"name": "Axel", "gender": "male", "style": "edgy, dramatic"},
    {"name": "Connor", "gender": "male", "style": "Irish accent, friendly"},
    {"name": "Cora", "gender": "female", "style": "mature, wise"},
    {"name": "Elena", "gender": "female", "style": "Mediterranean, passionate"},
    {"name": "Eli", "gender": "male", "style": "young, enthusiastic"},
    {"name": "Everett", "gender": "male", "style": "calm, measured"},
    {"name": "Gabriel", "gender": "male", "style": "romantic, smooth"},
    {"name": "Gianna", "gender": "female", "style": "Italian, expressive"},
    {"name": "Henry", "gender": "male", "style": "classic, refined"},
    {"name": "Ian", "gender": "male", "style": "Scottish, rugged"},
    {"name": "Jade", "gender": "female", "style": "mysterious, alluring"},
    {"name": "Jeremiah", "gender": "male", "style": "preacher, powerful"},
    {"name": "Jordan", "gender": "neutral", "style": "news anchor, clear"},
    {"name": "Julian", "gender": "male", "style": "artistic, thoughtful"},
    {"name": "Layla", "gender": "female", "style": "Middle Eastern, warm"},
    {"name": "Leonardo", "gender": "male", "style": "Italian, charismatic"},
    {"name": "Miles", "gender": "male", "style": "jazz, smooth"},
]

VOICES_DIR = Path("voices")
EMBEDDINGS_DIR = Path("embeddings")


def create_placeholder_voices():
    """
    Create placeholder voice entries.
    
    In production, you would:
    1. Upload actual voice reference WAV files to voices/
    2. Run this script to create embedding entries
    
    For now, this creates the directory structure and metadata.
    """
    VOICES_DIR.mkdir(exist_ok=True)
    EMBEDDINGS_DIR.mkdir(exist_ok=True)
    
    print("=" * 60)
    print("IndexTTS2 Voice Setup")
    print("=" * 60)
    print()
    print("This script sets up the voice directory structure.")
    print("You need to add actual voice reference files!")
    print()
    
    # Create voice metadata
    voices_meta = []
    
    for voice in VOICE_DEFINITIONS:
        name = voice["name"]
        
        # Check if voice audio exists
        audio_exists = False
        audio_path = None
        for ext in [".wav", ".mp3", ".flac"]:
            path = VOICES_DIR / f"{name}{ext}"
            if path.exists():
                audio_exists = True
                audio_path = str(path)
                break
        
        # Create embedding entry
        embedding_data = {
            "name": name,
            "gender": voice["gender"],
            "style": voice["style"],
            "audio_path": audio_path,
            "audio_exists": audio_exists
        }
        
        embedding_path = EMBEDDINGS_DIR / f"{name}.json"
        with open(embedding_path, "w") as f:
            json.dump(embedding_data, f, indent=2)
        
        status = "✓ Ready" if audio_exists else "⚠ Need audio"
        print(f"  {name:15} - {voice['gender']:8} - {status}")
        
        voices_meta.append(embedding_data)
    
    # Save master list
    with open(EMBEDDINGS_DIR / "_voices.json", "w") as f:
        json.dump(voices_meta, f, indent=2)
    
    print()
    print("=" * 60)
    print(f"Created {len(VOICE_DEFINITIONS)} voice entries")
    print()
    print("NEXT STEPS:")
    print("1. Add voice reference audio files to voices/")
    print("   Example: voices/Emily.wav (5-30 seconds of clear speech)")
    print()
    print("2. Run this script again to update status")
    print()
    print("3. Start the server: python server.py")
    print("=" * 60)


def download_sample_voices():
    """
    Download sample voice files from a public source.
    
    Note: In production, you should provide your own voice samples
    or use licensed voice recordings.
    """
    print("Note: You need to provide your own voice reference files.")
    print("Place WAV files (5-30 seconds each) in the voices/ directory.")
    print()
    print("Voice file naming: voices/{VoiceName}.wav")
    print("Example: voices/Emily.wav, voices/Michael.wav, etc.")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--download":
        download_sample_voices()
    
    create_placeholder_voices()
