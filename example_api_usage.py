"""
Simple example of using Cheap TTS API
For your personal projects - FREE unlimited access with your admin key
"""

import requests
import os

# Your personal admin API key (FREE unlimited access)
API_KEY = "ctts_d6Se8k94A4QV0hGSxjXDan1lh4rANki5CjrEk9tk0Ww"

# API endpoint (change this when you deploy)
BASE_URL = "http://localhost:5000"


def text_to_speech(text, voice="en-US-AriaNeural", rate="+0%", volume="+0%", pitch="+0Hz"):
    """
    Convert text to speech using Cheap TTS API
    
    Args:
        text: The text to convert to speech
        voice: Voice to use (default: en-US-AriaNeural)
        rate: Speech rate -50% to +100% (default: +0%)
        volume: Volume -50% to +50% (default: +0%)
        pitch: Pitch -200Hz to +200Hz (default: +0Hz)
    
    Returns:
        dict with 'success', 'audio_url', and 'filename'
    """
    
    response = requests.post(
        f"{BASE_URL}/api/v1/synthesize",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY
        },
        json={
            "text": text,
            "voice": voice,
            "rate": rate,
            "volume": volume,
            "pitch": pitch
        }
    )
    
    return response.json()


def download_audio(audio_url, filename="output.mp3"):
    """Download the audio file from the URL"""
    response = requests.get(audio_url)
    
    if response.status_code == 200:
        with open(filename, "wb") as f:
            f.write(response.content)
        print(f"✅ Audio saved to {filename}")
        return True
    else:
        print(f"❌ Error downloading audio: {response.status_code}")
        return False


def get_available_voices():
    """Get list of all available voices"""
    response = requests.get(f"{BASE_URL}/api/v1/voices")
    return response.json()


if __name__ == "__main__":
    print("🎤 Cheap TTS API Example\n")
    
    # Example 1: Simple text to speech
    print("1. Generating speech...")
    result = text_to_speech("Hello! This is a test of the Cheap TTS API.")
    
    if result["success"]:
        print(f"✅ Success! Audio URL: {result['audio_url']}")
        download_audio(result["audio_url"], "example1.mp3")
    else:
        print(f"❌ Error: {result.get('error')}")
    
    print()
    
    # Example 2: Different voice
    print("2. Generating speech with male voice...")
    result = text_to_speech(
        "Hi, I'm Guy, a male voice from the United States.",
        voice="en-US-GuyNeural"
    )
    
    if result["success"]:
        print(f"✅ Success!")
        download_audio(result["audio_url"], "example2_guy.mp3")
    else:
        print(f"❌ Error: {result.get('error')}")
    
    print()
    
    # Example 3: Faster speech
    print("3. Generating faster speech...")
    result = text_to_speech(
        "This speech is 50 percent faster than normal!",
        rate="+50%"
    )
    
    if result["success"]:
        print(f"✅ Success!")
        download_audio(result["audio_url"], "example3_faster.mp3")
    else:
        print(f"❌ Error: {result.get('error')}")
    
    print()
    
    # Example 4: List available voices
    print("4. Getting available voices...")
    voices = get_available_voices()
    
    if voices["success"]:
        print(f"✅ Found {voices['count']} voices!")
        print("\nPopular English voices:")
        for voice in voices["voices"][:10]:  # Show first 10
            print(f"  - {voice['short_name']}: {voice['local_name']} ({voice['gender']})")
    else:
        print(f"❌ Error: {voices.get('error')}")
    
    print("\n✨ Done! Check the generated MP3 files.")
