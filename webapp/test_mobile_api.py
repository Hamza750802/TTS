"""Test Mobile App API endpoints with real user credentials"""
import requests
import json

BASE = "http://127.0.0.1:5000"

print("=" * 60)
print("MOBILE APP API TEST")
print("=" * 60)

# 1. Login via mobile API
print("\n[1] MOBILE LOGIN: /api/v1/auth/login")
login_resp = requests.post(f"{BASE}/api/v1/auth/login", json={
    "email": "hamzaarshad15121@gmail.com",
    "password": "kawaki1012"
})
print(f"    Status: {login_resp.status_code}")

try:
    login_data = login_resp.json()
    print(f"    success: {login_data.get('success')}")
    
    if login_data.get('success'):
        token = login_data.get('token')
        user = login_data.get('user', {})
        print(f"    token: {token[:20]}..." if token else "    token: None")
        print(f"    user.email: {user.get('email')}")
        print(f"    user.is_subscribed: {user.get('is_subscribed')}")
        print(f"    user.subscription_type: {user.get('subscription_type')}")
        print(f"    user.chars_used: {user.get('chars_used')}")
        print(f"    user.chars_limit: {user.get('chars_limit')}")
        print(f"    user.chars_remaining: {user.get('chars_remaining')}")
    else:
        print(f"    error: {login_data.get('error')}")
        token = None
except Exception as e:
    print(f"    ERROR parsing response: {e}")
    print(f"    Raw: {login_resp.text[:500]}")
    token = None

if not token:
    print("\nLogin failed - cannot continue tests")
    exit(1)

# Set auth header
headers = {"Authorization": f"Bearer {token}"}

# 2. Get user info
print("\n[2] GET USER INFO: /api/v1/auth/me")
me_resp = requests.get(f"{BASE}/api/v1/auth/me", headers=headers)
print(f"    Status: {me_resp.status_code}")
try:
    me_data = me_resp.json()
    print(f"    success: {me_data.get('success')}")
    user = me_data.get('user', {})
    print(f"    is_subscribed: {user.get('is_subscribed')}")
    print(f"    chars_used: {user.get('chars_used')}")
    print(f"    chars_limit: {user.get('chars_limit')}")
    print(f"    chars_remaining: {user.get('chars_remaining')}")
except Exception as e:
    print(f"    ERROR: {e}")

# 3. Get voices
print("\n[3] GET VOICES: /api/voices")
voices_resp = requests.get(f"{BASE}/api/voices", headers=headers)
print(f"    Status: {voices_resp.status_code}")
try:
    voices_data = voices_resp.json()
    print(f"    success: {voices_data.get('success')}")
    print(f"    voice_count: {len(voices_data.get('voices', []))}")
except Exception as e:
    print(f"    ERROR: {e}")

# 4. Generate TTS via mobile endpoint
print("\n[4] MOBILE TTS: /api/v1/mobile/synthesize")
tts_resp = requests.post(f"{BASE}/api/v1/mobile/synthesize", 
    headers=headers,
    json={
        "text": "Testing mobile app text to speech generation.",
        "voice": "en-US-EmmaMultilingualNeural",
        "rate": 0,
        "pitch": 0
    }
)
print(f"    Status: {tts_resp.status_code}")
try:
    tts_data = tts_resp.json()
    print(f"    success: {tts_data.get('success')}")
    print(f"    audio_url: {tts_data.get('audio_url', 'N/A')}")
    print(f"    filename: {tts_data.get('filename', 'N/A')}")
    print(f"    chars_used: {tts_data.get('chars_used', 'N/A')}")
    print(f"    chars_remaining: {tts_data.get('chars_remaining', 'N/A')}")
    print(f"    chars_limit: {tts_data.get('chars_limit', 'N/A')}")
    
    if tts_data.get('error'):
        print(f"    error: {tts_data.get('error')}")
except Exception as e:
    print(f"    ERROR: {e}")
    print(f"    Raw: {tts_resp.text[:500]}")

# 5. Download audio
audio_url = tts_data.get('audio_url') if tts_data else None
if audio_url:
    print("\n[5] DOWNLOAD AUDIO")
    if not audio_url.startswith('http'):
        audio_url = f"{BASE}{audio_url}"
    audio_resp = requests.get(audio_url, headers=headers)
    print(f"    URL: {audio_url}")
    print(f"    Status: {audio_resp.status_code}")
    print(f"    Size: {len(audio_resp.content)} bytes")

print("\n" + "=" * 60)
print("MOBILE API TEST COMPLETE")
print("=" * 60)
