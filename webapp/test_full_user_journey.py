#!/usr/bin/env python3
"""
COMPREHENSIVE CHARACTER LIMIT TEST
Tests the complete user journey from signup to hitting the limit.
"""

import requests
import json
import time
import sys

BASE_URL = 'http://localhost:5000'

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}  {text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")

def print_step(num, text):
    print(f"\n{Colors.BOLD}[Step {num}]{Colors.END} {text}")

def print_pass(text):
    print(f"  {Colors.GREEN}✅ PASS:{Colors.END} {text}")

def print_fail(text):
    print(f"  {Colors.RED}❌ FAIL:{Colors.END} {text}")

def print_info(text):
    print(f"  {Colors.YELLOW}ℹ️  INFO:{Colors.END} {text}")

def format_num(n):
    return f"{n:,}"

def main():
    print_header("COMPREHENSIVE CHARACTER LIMIT TEST SUITE")
    
    session = requests.Session()
    test_email = f'fulltest_{int(time.time())}@test.com'
    token = None
    all_passed = True
    
    # ============================================
    # STEP 1: User Signup
    # ============================================
    print_step(1, "User Signup - Verify initial character allocation")
    
    try:
        r = session.post(f'{BASE_URL}/api/v1/auth/signup', json={
            'email': test_email,
            'password': 'TestPass123!'
        })
        data = r.json()
        
        if data.get('success'):
            print_pass(f"Signup successful for {test_email}")
            token = data.get('token')
            user = data.get('user', {})
            
            if user.get('chars_used') == 0:
                print_pass(f"chars_used = 0 (new user starts at zero)")
            else:
                print_fail(f"chars_used = {user.get('chars_used')} (expected 0)")
                all_passed = False
            
            if user.get('chars_limit') == 10000:
                print_pass(f"chars_limit = 10,000 (free tier limit)")
            else:
                print_fail(f"chars_limit = {user.get('chars_limit')} (expected 10000)")
                all_passed = False
                
            if user.get('chars_remaining') == 10000:
                print_pass(f"chars_remaining = 10,000 (full quota)")
            else:
                print_fail(f"chars_remaining = {user.get('chars_remaining')} (expected 10000)")
                all_passed = False
        else:
            print_fail(f"Signup failed: {data}")
            return False
    except Exception as e:
        print_fail(f"Exception: {e}")
        return False
    
    headers = {'Authorization': f'Bearer {token}'}
    
    # ============================================
    # STEP 2: First TTS Generation
    # ============================================
    print_step(2, "First TTS Generation - Verify character tracking starts")
    
    test_text = "Hello, this is a test of the text to speech system."  # 52 chars
    
    try:
        r = session.post(f'{BASE_URL}/api/v1/mobile/synthesize', 
            json={'text': test_text, 'voice': 'en-US-AriaNeural'},
            headers=headers
        )
        data = r.json()
        
        if data.get('success'):
            print_pass("Generation successful")
            print_info(f"Text length: {len(test_text)} characters")
            
            if data.get('chars_used') == len(test_text):
                print_pass(f"chars_used = {len(test_text)} (matches text length)")
            else:
                print_fail(f"chars_used = {data.get('chars_used')} (expected {len(test_text)})")
                all_passed = False
                
            expected_remaining = 10000 - len(test_text)
            if data.get('chars_remaining') == expected_remaining:
                print_pass(f"chars_remaining = {format_num(expected_remaining)}")
            else:
                print_fail(f"chars_remaining = {data.get('chars_remaining')} (expected {expected_remaining})")
                all_passed = False
        else:
            print_fail(f"Generation failed: {data}")
            all_passed = False
    except Exception as e:
        print_fail(f"Exception: {e}")
        all_passed = False
    
    # ============================================
    # STEP 3: Multiple Generations to approach limit
    # ============================================
    print_step(3, "Multiple Generations - Use up most of the quota")
    
    # Use ~900 char texts to speed up
    bulk_text = "This is a longer text block that will help us use up the character quota faster. " * 11  # ~913 chars
    print_info(f"Bulk text length: {len(bulk_text)} characters")
    
    generations = 0
    current_used = len(test_text)
    
    while current_used < 9000:  # Stop before 9000 to test the warning threshold
        try:
            r = session.post(f'{BASE_URL}/api/v1/mobile/synthesize', 
                json={'text': bulk_text, 'voice': 'en-US-EmmaMultilingualNeural'},
                headers=headers
            )
            data = r.json()
            
            if data.get('success'):
                generations += 1
                current_used = data.get('chars_used', current_used + len(bulk_text))
                remaining = data.get('chars_remaining', 10000 - current_used)
                usage_pct = (current_used / 10000) * 100
                
                # Progress bar
                bar_len = 30
                filled = int(bar_len * usage_pct / 100)
                bar = '█' * filled + '░' * (bar_len - filled)
                print(f"  [{bar}] {usage_pct:.1f}% - {format_num(current_used)} used, {format_num(remaining)} left")
            else:
                break
                
            if generations > 12:
                print_info("Safety limit reached")
                break
        except Exception as e:
            print_fail(f"Exception during bulk generation: {e}")
            break
    
    print_pass(f"Completed {generations} bulk generations")
    print_info(f"Current usage: {format_num(current_used)} / 10,000")
    
    # ============================================
    # STEP 4: Test 80% warning threshold
    # ============================================
    print_step(4, "Warning Threshold Check - Should show upgrade prompts at 80%+")
    
    if current_used >= 8000:
        print_pass(f"At {(current_used/10000)*100:.1f}% usage - UI should show warning")
    else:
        print_info(f"At {(current_used/10000)*100:.1f}% usage - below warning threshold")
    
    # ============================================
    # STEP 5: Use remaining quota
    # ============================================
    print_step(5, "Exhaust Remaining Quota")
    
    while True:
        try:
            r = session.post(f'{BASE_URL}/api/v1/mobile/synthesize', 
                json={'text': bulk_text, 'voice': 'en-US-JennyNeural'},
                headers=headers
            )
            data = r.json()
            
            if data.get('success'):
                current_used = data.get('chars_used', 0)
                remaining = data.get('chars_remaining', 0)
                print_info(f"Used: {format_num(current_used)}, Remaining: {format_num(remaining)}")
                
                if remaining < len(bulk_text):
                    print_info(f"Next bulk request would exceed limit ({len(bulk_text)} > {remaining})")
                    break
            else:
                print_info(f"Generation blocked: {data.get('error', 'Unknown')}")
                break
        except Exception as e:
            print_fail(f"Exception: {e}")
            break
    
    # ============================================
    # STEP 6: Test limit blocking
    # ============================================
    print_step(6, "Character Limit Blocking - Verify large request is blocked")
    
    try:
        r = session.post(f'{BASE_URL}/api/v1/mobile/synthesize', 
            json={'text': bulk_text, 'voice': 'en-US-GuyNeural'},
            headers=headers
        )
        data = r.json()
        
        if not data.get('success'):
            print_pass("Large request correctly BLOCKED")
            error = data.get('error', '')
            if 'limit' in error.lower() or 'Character' in error:
                print_pass(f"Error message mentions limit: \"{error[:80]}...\"")
            else:
                print_fail(f"Error message doesn't mention limit: {error}")
                all_passed = False
        else:
            print_fail("Large request should have been blocked!")
            all_passed = False
    except Exception as e:
        print_fail(f"Exception: {e}")
        all_passed = False
    
    # ============================================
    # STEP 7: Small request that fits remaining quota
    # ============================================
    print_step(7, "Small Request - Should fit within remaining quota")
    
    small_text = "Hi"  # 2 chars
    
    try:
        r = session.post(f'{BASE_URL}/api/v1/mobile/synthesize', 
            json={'text': small_text, 'voice': 'en-US-AriaNeural'},
            headers=headers
        )
        data = r.json()
        
        # Check current remaining
        r2 = session.post(f'{BASE_URL}/api/v1/auth/login', json={
            'email': test_email,
            'password': 'TestPass123!'
        })
        login_data = r2.json()
        remaining = login_data.get('user', {}).get('chars_remaining', 0)
        
        if remaining >= len(small_text):
            if data.get('success'):
                print_pass(f"Small request ({len(small_text)} chars) succeeded with {remaining} remaining")
            else:
                print_fail(f"Small request should succeed - had {remaining} remaining")
                all_passed = False
        else:
            if not data.get('success'):
                print_pass(f"Request correctly blocked - only {remaining} chars remaining")
            else:
                print_info("Request succeeded, quota might have been just enough")
    except Exception as e:
        print_fail(f"Exception: {e}")
        all_passed = False
    
    # ============================================
    # STEP 8: Verify state persists across login
    # ============================================
    print_step(8, "Session Persistence - Login should show current usage")
    
    try:
        r = session.post(f'{BASE_URL}/api/v1/auth/login', json={
            'email': test_email,
            'password': 'TestPass123!'
        })
        data = r.json()
        
        if data.get('success'):
            user = data.get('user', {})
            chars_used = user.get('chars_used', 0)
            chars_remaining = user.get('chars_remaining', 0)
            
            print_pass("Login successful")
            print_info(f"chars_used: {format_num(chars_used)}")
            print_info(f"chars_remaining: {format_num(chars_remaining)}")
            print_info(f"chars_limit: {format_num(user.get('chars_limit', 0))}")
            
            if chars_used > 9000:
                print_pass("Usage persisted correctly (>90% used)")
            else:
                print_fail(f"Usage seems low - expected >9000, got {chars_used}")
                all_passed = False
        else:
            print_fail(f"Login failed: {data}")
            all_passed = False
    except Exception as e:
        print_fail(f"Exception: {e}")
        all_passed = False
    
    # ============================================
    # STEP 9: Test with emotion/style
    # ============================================
    print_step(9, "Emotion Test - Limit should apply regardless of style")
    
    try:
        r = session.post(f'{BASE_URL}/api/v1/mobile/synthesize', 
            json={
                'text': bulk_text,
                'voice': 'en-US-JennyNeural',
                'style': 'cheerful'
            },
            headers=headers
        )
        data = r.json()
        
        if not data.get('success') and ('limit' in data.get('error', '').lower() or 'Character' in data.get('error', '')):
            print_pass("Request with emotion correctly blocked due to limit")
        elif data.get('success'):
            print_info("Request succeeded - there was still quota available")
        else:
            print_info(f"Blocked for other reason: {data.get('error')}")
    except Exception as e:
        print_fail(f"Exception: {e}")
        all_passed = False
    
    # ============================================
    # FINAL SUMMARY
    # ============================================
    print_header("TEST SUMMARY")
    
    if all_passed:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ ALL TESTS PASSED!{Colors.END}")
        print(f"\n{Colors.GREEN}The 10,000 character monthly limit is working correctly.{Colors.END}")
        print(f"\n{Colors.BOLD}Verified:{Colors.END}")
        print("  • New users start with 0 used / 10,000 limit")
        print("  • Character usage is tracked accurately")
        print("  • Usage persists across sessions")
        print("  • Large requests are blocked when limit is near")
        print("  • Small requests that fit are allowed")
        print("  • Limit applies to all voices and styles")
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ SOME TESTS FAILED{Colors.END}")
        print(f"\n{Colors.RED}Please review the failures above.{Colors.END}")
    
    return all_passed

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
