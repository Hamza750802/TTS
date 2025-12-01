"""Test the signup/dashboard flow as a real user would experience it"""
import requests
import time
import sys
import re

# Redirect output to file for visibility
log_file = open('C:/TTS-main/webapp/test_output.txt', 'w')
def log(msg):
    print(msg)
    log_file.write(msg + '\n')
    log_file.flush()

# Quick server check first
try:
    r = requests.get('http://localhost:5000/', timeout=2)
    log("Server is running!")
except requests.exceptions.ConnectionError:
    log("ERROR: Server is not running at http://localhost:5000")
    log("Please start it with: python app.py")
    log_file.close()
    sys.exit(1)

s = requests.Session()
base = 'http://localhost:5000'

# Create unique test user
email = f'testuser_{int(time.time())}@test.com'
password = 'Test123!'

log("="*60)
log("TESTING USER SIGNUP FLOW")
log("="*60)

# Step 0: Get CSRF token from signup page
log('\nStep 0: Getting CSRF token...')
r = s.get(f'{base}/signup')
csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text)
if not csrf_match:
    # Try alternative pattern
    csrf_match = re.search(r'csrf_token["\s:]+["\']([^"\']+)["\']', r.text)
if csrf_match:
    csrf_token = csrf_match.group(1)
    log(f'  CSRF token found: {csrf_token[:20]}...')
else:
    log('  WARNING: No CSRF token found, proceeding without it')
    csrf_token = None

# Step 1: Sign up
log('\nStep 1: Signing up new user...')
log(f'  Email: {email}')
form_data = {'email': email, 'password': password}
if csrf_token:
    form_data['csrf_token'] = csrf_token
r = s.post(f'{base}/signup', data=form_data, allow_redirects=False)
log(f'  Status: {r.status_code}')
redirect_url = r.headers.get('Location', 'none')
log(f'  Redirect to: {redirect_url}')

if r.status_code != 302:
    log(f'  ERROR: Expected 302 redirect, got {r.status_code}')
    log(f'  Response: {r.text[:500]}')
    log_file.close()
    exit(1)

# Step 2: Follow redirect to dashboard
log('\nStep 2: Following redirect to dashboard...')
r = s.get(f'{base}{redirect_url}' if redirect_url.startswith('/') else redirect_url)
log(f'  Status: {r.status_code}')

if r.status_code == 200:
    log('  SUCCESS - Dashboard loaded!')
    
    # Check for key elements
    checks = [
        ('Character usage info', 'character' in r.text.lower()),
        ('Generate button', 'generate' in r.text.lower()),
        ('Voice selector', 'voice' in r.text.lower()),
        ('Text input', 'textarea' in r.text.lower() or 'text-input' in r.text.lower()),
    ]
    
    log('\n  Dashboard elements:')
    for name, present in checks:
        status = 'OK' if present else 'MISSING'
        log(f'    [{status}] {name}')
        
elif r.status_code == 500:
    log('  ERROR: Internal Server Error')
    log(f'  Response: {r.text[:500]}')
else:
    log(f'  ERROR: Unexpected status {r.status_code}')
    log(f'  Response: {r.text[:500]}')

# Step 3: Try to generate speech (test the synthesis endpoint)
log('\nStep 3: Testing TTS generation...')
test_text = "Hello, this is a test of the text to speech system."
r = s.post(f'{base}/api/generate', json={
    'text': test_text,
    'voice': 'en-US-AriaNeural',
    'rate': '+0%',
    'volume': '+0%',
    'pitch': '+0Hz'
}, headers={'Content-Type': 'application/json'})
log(f'  Status: {r.status_code}')

if r.status_code == 200:
    data = r.json()
    log('  SUCCESS - Audio generated!')
    log(f'    chars_used: {data.get("chars_used", "N/A")}')
    log(f'    chars_remaining: {data.get("chars_remaining", "N/A")}')
elif r.status_code == 402:
    log('  Character limit reached (expected for exhausted accounts)')
else:
    log(f'  Response: {r.text[:300]}')

log("\n" + "="*60)
log("TEST COMPLETE")
log("="*60)
log_file.close()
