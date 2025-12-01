"""Complete test - login, dashboard, voices, TTS generation"""
import requests
import re
import json

s = requests.Session()
base = 'http://localhost:5000'

print("="*60)
print("COMPLETE USER FLOW TEST")
print("="*60)

# 1. Login
print("\n[1] LOGIN")
r = s.get(f'{base}/login')
csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text)
csrf_token = csrf.group(1) if csrf else None

r = s.post(f'{base}/login', data={
    'email': 'hamzaarshad15121@gmail.com',
    'password': 'kawaki1012',
    'csrf_token': csrf_token
}, allow_redirects=False)
print(f"    Status: {r.status_code}")
print(f"    Redirect: {r.headers.get('Location', 'none')}")

# 2. Dashboard
print("\n[2] DASHBOARD")
r = s.get(f'{base}/dashboard')
print(f"    Status: {r.status_code}")
if r.status_code == 200:
    if 'Text-to-Speech Studio' in r.text:
        print("    ✓ TTS Studio loaded")
    if 'FREE PLAN' in r.text:
        print("    ✓ FREE PLAN badge")
else:
    print(f"    ERROR: {r.text[:300]}")

# 3. Voices API
print("\n[3] VOICES API (/api/voices)")
r = s.get(f'{base}/api/voices')
print(f"    Status: {r.status_code}")
if r.status_code == 200:
    try:
        data = r.json()
        voices = data.get('voices', [])
        print(f"    ✓ Got {len(voices)} voices")
        if voices:
            print(f"    First voice: {voices[0].get('ShortName', 'unknown')}")
    except:
        print(f"    Response: {r.text[:200]}")
else:
    print(f"    ERROR: {r.text[:300]}")

# 4. TTS Generation
print("\n[4] TTS GENERATION")
r = s.post(f'{base}/api/generate', json={
    'text': 'Hello, testing the text to speech.',
    'voice': 'en-US-AriaNeural',
    'rate': '+0%',
    'pitch': '+0Hz',
    'volume': '+0%'
})
print(f"    Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"    ✓ Audio generated!")
    print(f"    chars_used: {data.get('chars_used')}")
    print(f"    chars_remaining: {data.get('chars_remaining')}")
    print(f"    audioUrl: {data.get('audioUrl', 'N/A')}")
else:
    print(f"    ERROR: {r.text[:300]}")

# 5. Test audio download
print("\n[5] AUDIO DOWNLOAD")
if r.status_code == 200 and data.get('audioUrl'):
    audio_url = data.get('audioUrl')
    r = s.get(f'{base}{audio_url}')
    print(f"    Status: {r.status_code}")
    if r.status_code == 200:
        print(f"    ✓ Audio file size: {len(r.content)} bytes")
    else:
        print(f"    ERROR: {r.text[:200]}")

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)
