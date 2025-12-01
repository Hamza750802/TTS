"""Test Mobile App API with a FREE user to verify character limits"""
import requests
import time

BASE = "http://127.0.0.1:5000"

print("=" * 60)
print("MOBILE APP - FREE USER TEST")
print("=" * 60)

# Create a new free user
test_email = f"mobiletest_{int(time.time())}@test.com"
test_password = "TestPass123!"

# 1. Signup via mobile API
print(f"\n[1] SIGNUP: {test_email}")
signup_resp = requests.post(f"{BASE}/api/v1/auth/signup", json={
    "email": test_email,
    "password": test_password
})
print(f"    Status: {signup_resp.status_code}")
try:
    data = signup_resp.json()
    print(f"    success: {data.get('success')}")
    if data.get('error'):
        print(f"    error: {data.get('error')}")
except:
    print(f"    Raw: {signup_resp.text[:300]}")

# 2. Login
print("\n[2] LOGIN")
login_resp = requests.post(f"{BASE}/api/v1/auth/login", json={
    "email": test_email,
    "password": test_password
})
print(f"    Status: {login_resp.status_code}")
login_data = login_resp.json()
print(f"    success: {login_data.get('success')}")

if login_data.get('success'):
    token = login_data.get('token')
    user = login_data.get('user', {})
    print(f"    is_subscribed: {user.get('is_subscribed')}")
    print(f"    chars_used: {user.get('chars_used')}")
    print(f"    chars_limit: {user.get('chars_limit')}")
    print(f"    chars_remaining: {user.get('chars_remaining')}")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. Generate some TTS
    print("\n[3] TTS GENERATION (46 chars)")
    tts_resp = requests.post(f"{BASE}/api/v1/mobile/synthesize",
        headers=headers,
        json={
            "text": "Testing free user character limits on mobile.",
            "voice": "en-US-EmmaMultilingualNeural",
            "rate": 0,
            "pitch": 0
        }
    )
    print(f"    Status: {tts_resp.status_code}")
    tts_data = tts_resp.json()
    print(f"    success: {tts_data.get('success')}")
    print(f"    chars_used: {tts_data.get('chars_used')}")
    print(f"    chars_remaining: {tts_data.get('chars_remaining')}")
    print(f"    chars_limit: {tts_data.get('chars_limit')}")
    
    # 4. Check /auth/me
    print("\n[4] CHECK USER STATUS")
    me_resp = requests.get(f"{BASE}/api/v1/auth/me", headers=headers)
    me_data = me_resp.json()
    user = me_data.get('user', {})
    print(f"    is_subscribed: {user.get('is_subscribed')}")
    print(f"    chars_used: {user.get('chars_used')}")
    print(f"    chars_limit: {user.get('chars_limit')}")
    print(f"    chars_remaining: {user.get('chars_remaining')}")
    
    # Verify free limit is 10000
    if user.get('chars_limit') == 10000:
        print("\n    ✓ FREE USER LIMIT CORRECTLY SET TO 10,000")
    else:
        print(f"\n    ✗ WRONG LIMIT! Expected 10000, got {user.get('chars_limit')}")

print("\n" + "=" * 60)
print("FREE USER TEST COMPLETE")
print("=" * 60)
