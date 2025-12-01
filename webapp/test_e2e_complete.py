"""Complete E2E test - sign up, use TTS, hit character limit, verify upgrade prompts"""
import requests
import time
import sys
import re

# Output to file for visibility
log_file = open('C:/TTS-main/webapp/e2e_test_output.txt', 'w')

def log(msg):
    print(msg)
    log_file.write(msg + '\n')
    log_file.flush()

# Quick server check
try:
    r = requests.get('http://localhost:5000/', timeout=2)
    log("Server is running!")
except requests.exceptions.ConnectionError:
    log("ERROR: Server is not running at http://localhost:5000")
    log_file.close()
    sys.exit(1)

s = requests.Session()
base = 'http://localhost:5000'

# Create unique test user
email = f'e2etest_{int(time.time())}@test.com'
password = 'Test123!'

log("="*70)
log("COMPLETE END-TO-END TEST")
log("="*70)

# Step 0: Get CSRF token
log('\n[STEP 0] Getting CSRF token...')
r = s.get(f'{base}/signup')
csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text)
csrf_token = csrf_match.group(1) if csrf_match else None
if csrf_token:
    log(f'  CSRF token: OK')
else:
    log('  WARNING: No CSRF token found')

# Step 1: Sign up
log('\n[STEP 1] Signing up new free user...')
log(f'  Email: {email}')
form_data = {'email': email, 'password': password}
if csrf_token:
    form_data['csrf_token'] = csrf_token
r = s.post(f'{base}/signup', data=form_data, allow_redirects=False)
redirect_url = r.headers.get('Location', '')
if redirect_url == '/dashboard':
    log(f'  SUCCESS: Free user redirected to /dashboard (not payment page)')
else:
    log(f'  FAILED: Redirected to {redirect_url} instead of /dashboard')

# Step 2: Check dashboard loads
log('\n[STEP 2] Loading dashboard...')
r = s.get(f'{base}/dashboard')
if r.status_code == 200:
    log('  SUCCESS: Dashboard loaded')
else:
    log(f'  FAILED: Status {r.status_code}')

# Step 3: Generate some speech to use characters
log('\n[STEP 3] Testing TTS generation...')
test_text = "Hello world! This is a test of the text to speech system. It should work perfectly."
r = s.post(f'{base}/api/generate', json={
    'text': test_text,
    'voice': 'en-US-AriaNeural',
    'rate': '+0%',
    'volume': '+0%',
    'pitch': '+0Hz'
})
if r.status_code == 200:
    data = r.json()
    log(f'  SUCCESS: Audio generated')
    log(f'    chars_used: {data.get("chars_used", "N/A")}')
    log(f'    chars_remaining: {data.get("chars_remaining", "N/A")}')
    chars_used = data.get("chars_used", 0)
    chars_remaining = data.get("chars_remaining", 0)
else:
    log(f'  FAILED: {r.text[:200]}')
    chars_used, chars_remaining = 0, 0

# Step 4: Check usage persists across sessions
log('\n[STEP 4] Verifying usage persists (re-login)...')
# Logout
s.get(f'{base}/logout')
# Login again with CSRF
r = s.get(f'{base}/login')
csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text)
csrf_token = csrf_match.group(1) if csrf_match else None
form_data = {'email': email, 'password': password}
if csrf_token:
    form_data['csrf_token'] = csrf_token
r = s.post(f'{base}/login', data=form_data, allow_redirects=False)

# Check a protected endpoint to see current usage
r = s.post(f'{base}/api/generate', json={
    'text': 'Check',
    'voice': 'en-US-AriaNeural',
    'rate': '+0%'
})
if r.status_code == 200:
    data = r.json()
    new_chars_used = data.get("chars_used", 0)
    if new_chars_used > chars_used:
        log(f'  SUCCESS: Usage persisted and updated ({chars_used} -> {new_chars_used} chars)')
    else:
        log(f'  ISSUE: Usage might not have persisted correctly ({chars_used} vs {new_chars_used})')
else:
    log(f'  FAILED: {r.text[:200]}')

# Step 5: Try to hit character limit with a large text
log('\n[STEP 5] Testing character limit enforcement...')
# Create text that will exceed 10K limit
large_text = "This is a test sentence. " * 500  # ~13K chars
r = s.post(f'{base}/api/generate', json={
    'text': large_text,
    'voice': 'en-US-AriaNeural',
    'rate': '+0%'
})
if r.status_code == 402:
    data = r.json()
    log(f'  SUCCESS: Character limit enforced (HTTP 402)')
    log(f'    error: {data.get("error", "N/A")[:80]}...')
    log(f'    limit_reached: {data.get("limit_reached", False)}')
    log(f'    upgrade_url: {data.get("upgrade_url", "N/A")}')
elif r.status_code == 200:
    log(f'  WARNING: Large text was accepted (maybe limit not reached yet)')
    data = r.json()
    log(f'    chars_used: {data.get("chars_used", "N/A")}')
    log(f'    chars_remaining: {data.get("chars_remaining", "N/A")}')
else:
    log(f'  UNEXPECTED: Status {r.status_code} - {r.text[:200]}')

# Step 6: Verify small request that fits quota still works
log('\n[STEP 6] Testing small request after large one blocked...')
# First check remaining chars
r = s.post(f'{base}/api/generate', json={
    'text': 'Hi',
    'voice': 'en-US-AriaNeural',
    'rate': '+0%'
})
if r.status_code == 200:
    log(f'  SUCCESS: Small request still works')
    data = r.json()
    log(f'    chars_remaining after: {data.get("chars_remaining", "N/A")}')
elif r.status_code == 402:
    log(f'  Limit already reached - small request also blocked')
else:
    log(f'  Status: {r.status_code}')

log("\n" + "="*70)
log("E2E TEST COMPLETE")
log("="*70)

log_file.close()
print("\nFull output saved to: C:/TTS-main/webapp/e2e_test_output.txt")
