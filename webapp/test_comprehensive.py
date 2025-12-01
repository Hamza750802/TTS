"""COMPREHENSIVE TEST OF ALL ENDPOINTS AND FEATURES
This test simulates a real user from signup to TTS generation.
"""
import requests
import re
import time

BASE = "http://127.0.0.1:5000"

def test_all():
    session = requests.Session()
    print("=" * 70)
    print("COMPREHENSIVE CHEAPTTS TESTING")
    print("=" * 70)
    
    results = []
    
    # ========================================
    # PUBLIC ENDPOINTS
    # ========================================
    print("\n" + "=" * 70)
    print("PART 1: PUBLIC ENDPOINTS (no auth)")
    print("=" * 70)
    
    # 1.1 Landing page
    r = requests.get(f"{BASE}/")
    results.append(("GET /", r.status_code == 200, r.status_code))
    print(f"[{'✓' if r.status_code == 200 else '✗'}] GET / - Status: {r.status_code}")
    
    # 1.2 Login page
    r = requests.get(f"{BASE}/login")
    results.append(("GET /login", r.status_code == 200, r.status_code))
    print(f"[{'✓' if r.status_code == 200 else '✗'}] GET /login - Status: {r.status_code}")
    
    # 1.3 Signup page
    r = requests.get(f"{BASE}/signup")
    results.append(("GET /signup", r.status_code == 200, r.status_code))
    print(f"[{'✓' if r.status_code == 200 else '✗'}] GET /signup - Status: {r.status_code}")
    
    # 1.4 Voices API (public)
    r = requests.get(f"{BASE}/api/voices")
    ok = r.status_code == 200 and r.json().get('success')
    voice_count = len(r.json().get('voices', [])) if ok else 0
    results.append(("GET /api/voices", ok, f"{r.status_code}, {voice_count} voices"))
    print(f"[{'✓' if ok else '✗'}] GET /api/voices - Status: {r.status_code}, Voices: {voice_count}")
    
    # 1.5 Presets API (public)
    r = requests.get(f"{BASE}/api/presets")
    ok = r.status_code == 200 and r.json().get('success')
    preset_count = len(r.json().get('presets', [])) if ok else 0
    results.append(("GET /api/presets", ok, f"{r.status_code}, {preset_count} presets"))
    print(f"[{'✓' if ok else '✗'}] GET /api/presets - Status: {r.status_code}, Presets: {preset_count}")
    
    # ========================================
    # AUTHENTICATION FLOW
    # ========================================
    print("\n" + "=" * 70)
    print("PART 2: AUTHENTICATION (login with test user)")
    print("=" * 70)
    
    # 2.1 Get CSRF token
    r = session.get(f"{BASE}/login")
    csrf_match = re.search(r'name="csrf_token"[^>]+value="([^"]+)"', r.text)
    csrf_token = csrf_match.group(1) if csrf_match else None
    results.append(("GET CSRF token", bool(csrf_token), "Found" if csrf_token else "NOT FOUND"))
    print(f"[{'✓' if csrf_token else '✗'}] CSRF Token - {'Found' if csrf_token else 'NOT FOUND'}")
    
    # 2.2 Login
    r = session.post(f"{BASE}/login", data={
        "csrf_token": csrf_token,
        "email": "hamzaarshad15121@gmail.com",
        "password": "kawaki1012"
    }, allow_redirects=False)
    ok = r.status_code == 302 and 'dashboard' in r.headers.get('Location', '')
    results.append(("POST /login", ok, f"{r.status_code} -> {r.headers.get('Location')}"))
    print(f"[{'✓' if ok else '✗'}] POST /login - Status: {r.status_code}, Redirect: {r.headers.get('Location')}")
    
    # ========================================
    # AUTHENTICATED ENDPOINTS
    # ========================================
    print("\n" + "=" * 70)
    print("PART 3: AUTHENTICATED ENDPOINTS")
    print("=" * 70)
    
    # 3.1 Dashboard
    r = session.get(f"{BASE}/dashboard")
    has_voice_select = 'id="voice"' in r.text
    has_free_badge = 'FREE PLAN' in r.text
    ok = r.status_code == 200 and has_voice_select
    results.append(("GET /dashboard", ok, f"{r.status_code}, voice_select={has_voice_select}, free_badge={has_free_badge}"))
    print(f"[{'✓' if ok else '✗'}] GET /dashboard - Status: {r.status_code}, Voice select: {has_voice_select}, FREE PLAN badge: {has_free_badge}")
    
    # 3.2 Voices API (authenticated)
    r = session.get(f"{BASE}/api/voices")
    ok = r.status_code == 200 and r.json().get('success')
    voice_count = len(r.json().get('voices', [])) if ok else 0
    styled_voices = len([v for v in r.json().get('voices', []) if v.get('has_styles')]) if ok else 0
    results.append(("GET /api/voices (auth)", ok, f"{voice_count} voices, {styled_voices} with emotions"))
    print(f"[{'✓' if ok else '✗'}] GET /api/voices - Voices: {voice_count}, With emotions: {styled_voices}")
    
    # 3.3 TTS Generation
    print("\n--- Testing TTS Generation ---")
    r = session.post(f"{BASE}/api/generate", json={
        "text": "Hello, this is a test of the text to speech generation.",
        "voice": "en-US-EmmaMultilingualNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "volume": "+0%"
    })
    ok = r.status_code == 200 and r.json().get('success')
    data = r.json() if ok else {}
    chars_used = data.get('chars_used', 'N/A')
    chars_remaining = data.get('chars_remaining', 'N/A')
    audio_url = data.get('audioUrl', 'N/A')
    results.append(("POST /api/generate", ok, f"chars_used={chars_used}, remaining={chars_remaining}"))
    print(f"[{'✓' if ok else '✗'}] POST /api/generate - Status: {r.status_code}")
    print(f"    chars_used: {chars_used}")
    print(f"    chars_remaining: {chars_remaining}")
    print(f"    audioUrl: {audio_url}")
    
    # 3.4 Audio download
    if audio_url and audio_url != 'N/A':
        r = session.get(f"{BASE}{audio_url}")
        ok = r.status_code == 200 and len(r.content) > 1000
        results.append(("GET audio file", ok, f"{len(r.content)} bytes"))
        print(f"[{'✓' if ok else '✗'}] GET {audio_url} - Size: {len(r.content)} bytes")
    
    # 3.5 Character limit check
    print("\n--- Testing Character Limit ---")
    r = session.get(f"{BASE}/api/voices")  # Just to get an authenticated page state
    r = session.get(f"{BASE}/dashboard")
    
    # Check usage info in page
    chars_limit_shown = "10000" in r.text or "10,000" in r.text or "chars_limit" in r.text
    print(f"    Character limit (10000) visible: {chars_limit_shown}")
    
    # ========================================
    # VOICE DETAILS CHECK
    # ========================================
    print("\n" + "=" * 70)
    print("PART 4: VOICE DETAILS")
    print("=" * 70)
    
    r = session.get(f"{BASE}/api/voices")
    voices = r.json().get('voices', [])
    
    # Popular voices
    emma_voices = [v for v in voices if 'Emma' in v.get('name', '')]
    jenny_voices = [v for v in voices if 'Jenny' in v.get('name', '')]
    guy_voices = [v for v in voices if 'Guy' in v.get('name', '')]
    
    print(f"    Emma voices: {len(emma_voices)}")
    print(f"    Jenny voices: {len(jenny_voices)}")  
    print(f"    Guy voices: {len(guy_voices)}")
    
    # Voices with styles
    styled = [v for v in voices if v.get('has_styles')]
    print(f"    Voices with emotion styles: {len(styled)}")
    if styled:
        print(f"    Sample styles: {styled[0].get('styles', [])[:5]}")
    
    # ========================================
    # SUMMARY
    # ========================================
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    
    print(f"\n✓ Passed: {passed}")
    print(f"✗ Failed: {failed}")
    
    if failed > 0:
        print("\nFailed tests:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}: {detail}")
    
    print("\n" + "=" * 70)
    if failed == 0:
        print("🎉 ALL TESTS PASSED!")
    else:
        print(f"⚠️ {failed} TEST(S) FAILED")
    print("=" * 70)
    
    return failed == 0

if __name__ == "__main__":
    success = test_all()
    exit(0 if success else 1)
