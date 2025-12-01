"""Test Mobile App Subscription Flow on Production"""
import requests
import json
import time

BASE = "https://cheaptts.com"
TEST_EMAIL = "michaelsmith045@protonmail.com"
TEST_PASSWORD = "kawaki1012"

print("=" * 60)
print("MOBILE APP SUBSCRIPTION FLOW TEST")
print(f"Target: {BASE}")
print(f"Test Email: {TEST_EMAIL}")
print("=" * 60)

# Step 1: Try to signup (might already exist)
print("\n[1] SIGNUP: /api/v1/auth/signup")
signup_resp = requests.post(f"{BASE}/api/v1/auth/signup", json={
    "email": TEST_EMAIL,
    "password": TEST_PASSWORD,
    "name": "Michael Smith"
}, timeout=30)
print(f"    Status: {signup_resp.status_code}")
try:
    signup_data = signup_resp.json()
    print(f"    Response: {json.dumps(signup_data, indent=6)}")
except Exception as e:
    print(f"    ERROR: {e}")
    print(f"    Raw: {signup_resp.text[:500]}")

# Step 2: Login
print("\n[2] LOGIN: /api/v1/auth/login")
login_resp = requests.post(f"{BASE}/api/v1/auth/login", json={
    "email": TEST_EMAIL,
    "password": TEST_PASSWORD
}, timeout=30)
print(f"    Status: {login_resp.status_code}")

token = None
try:
    login_data = login_resp.json()
    print(f"    success: {login_data.get('success')}")
    
    if login_data.get('success'):
        token = login_data.get('token')
        user = login_data.get('user', {})
        print(f"    token: {token[:30]}..." if token else "    token: None")
        print(f"    === USER INFO ===")
        print(f"    email: {user.get('email')}")
        print(f"    name: {user.get('name')}")
        print(f"    is_subscribed: {user.get('is_subscribed')}")
        print(f"    subscription_type: {user.get('subscription_type')}")
        print(f"    chars_used: {user.get('chars_used')}")
        print(f"    chars_limit: {user.get('chars_limit')}")
        print(f"    chars_remaining: {user.get('chars_remaining')}")
    else:
        print(f"    error: {login_data.get('error')}")
except Exception as e:
    print(f"    ERROR: {e}")
    print(f"    Raw: {login_resp.text[:500]}")

if not token:
    print("\n❌ Login failed - cannot continue tests")
    exit(1)

headers = {"Authorization": f"Bearer {token}"}

# Step 3: Get user info via /me endpoint
print("\n[3] GET USER INFO: /api/v1/auth/me")
me_resp = requests.get(f"{BASE}/api/v1/auth/me", headers=headers, timeout=30)
print(f"    Status: {me_resp.status_code}")
try:
    me_data = me_resp.json()
    print(f"    success: {me_data.get('success')}")
    user = me_data.get('user', {})
    print(f"    === FROM /me ENDPOINT ===")
    print(f"    is_subscribed: {user.get('is_subscribed')}")
    print(f"    subscription_type: {user.get('subscription_type')}")
    print(f"    chars_used: {user.get('chars_used')}")
    print(f"    chars_limit: {user.get('chars_limit')}")
    print(f"    chars_remaining: {user.get('chars_remaining')}")
except Exception as e:
    print(f"    ERROR: {e}")

# Step 4: Get usage stats
print("\n[4] GET USAGE: /api/v1/usage")
usage_resp = requests.get(f"{BASE}/api/v1/usage", headers=headers, timeout=30)
print(f"    Status: {usage_resp.status_code}")
try:
    usage_data = usage_resp.json()
    print(f"    Response: {json.dumps(usage_data, indent=6)}")
except Exception as e:
    print(f"    ERROR: {e}")

# Step 5: Test TTS generation (should work for free tier with 10K chars)
print("\n[5] TTS GENERATION: /api/v1/mobile/synthesize")
tts_resp = requests.post(f"{BASE}/api/v1/mobile/synthesize", 
    headers=headers,
    json={
        "text": "Hello! This is a test of the mobile app text to speech.",
        "voice": "en-US-EmmaMultilingualNeural"
    },
    timeout=60
)
print(f"    Status: {tts_resp.status_code}")
try:
    tts_data = tts_resp.json()
    print(f"    success: {tts_data.get('success')}")
    if tts_data.get('success'):
        print(f"    audio_url: {tts_data.get('audio_url', 'N/A')}")
        print(f"    chars_used: {tts_data.get('chars_used', 'N/A')}")
        print(f"    chars_remaining: {tts_data.get('chars_remaining', 'N/A')}")
        print(f"    chars_limit: {tts_data.get('chars_limit', 'N/A')}")
    else:
        print(f"    error: {tts_data.get('error')}")
except Exception as e:
    print(f"    ERROR: {e}")
    print(f"    Raw: {tts_resp.text[:500]}")

# Step 6: Verify updated usage after TTS
print("\n[6] VERIFY USAGE AFTER TTS: /api/v1/auth/me")
me_resp2 = requests.get(f"{BASE}/api/v1/auth/me", headers=headers, timeout=30)
print(f"    Status: {me_resp2.status_code}")
try:
    me_data2 = me_resp2.json()
    user2 = me_data2.get('user', {})
    print(f"    chars_used (after): {user2.get('chars_used')}")
    print(f"    chars_remaining (after): {user2.get('chars_remaining')}")
except Exception as e:
    print(f"    ERROR: {e}")

print("\n" + "=" * 60)
print("SUBSCRIPTION FLOW TEST SUMMARY")
print("=" * 60)
print("""
Expected for FREE USER:
  - is_subscribed: False
  - chars_limit: 10000
  - chars_remaining: 10000 - chars_used
  - TTS should work until limit reached

Expected for PRO USER:
  - is_subscribed: True
  - chars_limit: 999999999
  - TTS should work without limit
""")
