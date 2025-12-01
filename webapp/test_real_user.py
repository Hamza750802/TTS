"""Test with real user account"""
import requests
import re

s = requests.Session()
base = 'http://localhost:5000'

# Get CSRF token from login page
r = s.get(f'{base}/login')
csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text)
csrf_token = csrf.group(1) if csrf else None
print(f'CSRF: OK')

# Login with your account
print('Logging in as hamzaarshad15121@gmail.com...')
r = s.post(f'{base}/login', data={
    'email': 'hamzaarshad15121@gmail.com',
    'password': 'kawaki1012',
    'csrf_token': csrf_token
}, allow_redirects=False)
print(f'Login status: {r.status_code}')
print(f'Redirect: {r.headers.get("Location", "none")}')

# Go to dashboard
print()
print('Accessing dashboard...')
r = s.get(f'{base}/dashboard')
print(f'Dashboard status: {r.status_code}')
if r.status_code == 500:
    print('ERROR 500!')
    error_match = re.search(r'<title>([^<]+)</title>', r.text)
    print(f'Error: {error_match.group(1) if error_match else r.text[:500]}')
elif r.status_code == 200:
    if 'Text-to-Speech Studio' in r.text:
        print('SUCCESS: TTS Studio loaded!')
        if 'FREE PLAN' in r.text:
            print('  - FREE PLAN badge visible')
        if 'UNLIMITED' in r.text:
            print('  - UNLIMITED badge visible')
        if 'Monthly Usage' in r.text:
            print('  - Usage card visible')
        if 'textarea' in r.text.lower():
            print('  - Text input area visible')
    elif 'Subscribe to unlock' in r.text:
        print('PROBLEM: Still showing subscribe page')
    else:
        print('Unknown page content')
        print(r.text[:500])

# Test TTS generation
print()
print('Testing TTS generation...')
r = s.post(f'{base}/api/generate', json={
    'text': 'Hello, this is a test.',
    'voice': 'en-US-AriaNeural',
    'rate': '+0%'
})
print(f'Generate status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'SUCCESS! chars_used={data.get("chars_used")}, remaining={data.get("chars_remaining")}')
else:
    print(f'Response: {r.text[:300]}')
