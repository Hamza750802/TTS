import requests
import time

s = requests.Session()
email = f'freetest_{int(time.time())}@test.com'

r = s.post('http://localhost:5000/signup', data={
    'email': email,
    'password': 'Test123!'
}, allow_redirects=False)

print('Signup status:', r.status_code)
loc = r.headers.get('Location', 'no redirect')
print('Redirect to:', loc)

if '/dashboard' in loc:
    print('✅ SUCCESS: User redirected to dashboard (not subscribe)')
elif '/subscribe' in loc:
    print('❌ FAIL: User still redirected to subscribe page')
else:
    print('? Unknown redirect')
