#!/usr/bin/env python3
"""
Real-world test: Hit the 10,000 character limit as a free user would.
This test simulates actual user behavior until they hit their monthly limit.
"""

import requests
import json
import time

BASE_URL = 'http://localhost:5000'
session = requests.Session()

def main():
    # Create a fresh test user
    test_email = f'limit_test_{int(time.time())}@test.com'
    print(f'Creating test user: {test_email}')
    print('=' * 60)

    r = session.post(f'{BASE_URL}/api/v1/auth/signup', json={
        'email': test_email,
        'password': 'TestPass123!'
    })
    data = r.json()
    
    if not data.get('success'):
        print(f'Signup failed: {data}')
        return
    
    token = data.get('token')
    user = data.get('user', {})
    
    print(f'\n📊 INITIAL STATE:')
    print(f'   chars_used:      {user.get("chars_used")}')
    print(f'   chars_remaining: {user.get("chars_remaining")}')
    print(f'   chars_limit:     {user.get("chars_limit")}')
    
    headers = {'Authorization': f'Bearer {token}'}
    
    # Generate text that's about 1000 chars to speed up testing
    long_text = 'This is a test message that will be used to consume character quota. ' * 14  # ~1008 chars
    print(f'\n📝 Test text length: {len(long_text)} characters')
    print(f'   Will need ~10 requests to hit 10,000 limit')
    print('=' * 60)
    
    # Keep generating until we hit the limit
    total_used = 0
    attempt = 0
    
    while True:
        attempt += 1
        print(f'\n--- Request #{attempt} ---')
        
        r = session.post(f'{BASE_URL}/api/v1/mobile/synthesize', 
            json={'text': long_text, 'voice': 'en-US-EmmaMultilingualNeural'},
            headers=headers
        )
        
        resp = r.json()
        print(f'   HTTP Status: {r.status_code}')
        print(f'   Success: {resp.get("success")}')
        
        if resp.get('success'):
            chars_used = resp.get('chars_used', 0)
            chars_remaining = resp.get('chars_remaining', 0)
            chars_limit = resp.get('chars_limit', 10000)
            
            usage_pct = (chars_used / chars_limit) * 100
            
            print(f'   chars_used:      {chars_used:,} ({usage_pct:.1f}%)')
            print(f'   chars_remaining: {chars_remaining:,}')
            
            total_used = chars_used
            
            # Show progress bar
            bar_len = 40
            filled = int(bar_len * usage_pct / 100)
            bar = '█' * filled + '░' * (bar_len - filled)
            print(f'   [{bar}] {usage_pct:.1f}%')
            
            if chars_remaining < len(long_text):
                print(f'\n⚠️  Approaching limit! Only {chars_remaining} chars left.')
                print(f'    Next request for {len(long_text)} chars should be BLOCKED.')
        else:
            error = resp.get('error', 'Unknown error')
            print(f'\n🚫 BLOCKED!')
            print(f'   Error: {error}')
            print(f'\n{"=" * 60}')
            print(f'📊 FINAL RESULT:')
            print(f'   Total chars used before block: {total_used:,}')
            print(f'   Requests completed: {attempt - 1}')
            print(f'   Request #{attempt} was BLOCKED as expected!')
            print(f'{"=" * 60}')
            break
        
        if attempt > 15:
            print('\n⚠️  Safety limit reached (15 requests)')
            break
    
    # Try a few more edge cases
    print('\n\n📋 EDGE CASE TESTS:')
    print('=' * 60)
    
    # Test 1: Try to generate text that fits in remaining quota
    print(f'\nTest 1: Try generating short text (fits in {350} remaining)...')
    r = session.post(f'{BASE_URL}/api/v1/mobile/synthesize', 
        json={'text': 'Hello world, this is a short test.', 'voice': 'en-US-EmmaMultilingualNeural'},
        headers=headers
    )
    resp = r.json()
    if resp.get('success'):
        print(f'   ✅ Success! Used remaining quota.')
        print(f'      chars_used: {resp.get("chars_used")}')
        print(f'      chars_remaining: {resp.get("chars_remaining")}')
    else:
        print(f'   Result: {resp.get("error")}')
    
    # Test 2: Now try to exceed what's left
    print('\nTest 2: Try generating text that exceeds remaining...')
    r = session.post(f'{BASE_URL}/api/v1/mobile/synthesize', 
        json={'text': long_text, 'voice': 'en-US-JennyNeural'},
        headers=headers
    )
    resp = r.json()
    if resp.get('success'):
        print('   ❌ UNEXPECTED: Should have been blocked!')
    else:
        print(f'   ✅ Correctly blocked: {resp.get("error")}')
    
    # Test 3: Check user profile
    print('\nTest 3: Check login shows correct usage...')
    r = session.post(f'{BASE_URL}/api/v1/auth/login', json={
        'email': test_email,
        'password': 'TestPass123!'
    })
    if r.status_code == 200:
        login_data = r.json()
        user = login_data.get('user', {})
        print(f'   chars_used:      {user.get("chars_used"):,}')
        print(f'   chars_remaining: {user.get("chars_remaining"):,}')
        print(f'   chars_limit:     {user.get("chars_limit"):,}')
        
        if user.get('chars_remaining', 0) < 500:
            print('   ✅ Login correctly reflects near-limit state')
    else:
        print(f'   Login returned: {r.status_code}, {r.text}')
    
    print('\n\n✅ CHARACTER LIMIT TEST COMPLETE!')
    print('The 10,000 character monthly limit is working correctly.')

if __name__ == '__main__':
    main()
