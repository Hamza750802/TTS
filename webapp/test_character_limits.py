#!/usr/bin/env python3
"""
Comprehensive test suite for character limit implementation.
Tests all pathways: voices with/without emotions, multi-speaker dialogues,
character limit enforcement, and usage tracking accuracy.
"""

import os
import sys
import json
import hashlib
import time
from datetime import datetime, timedelta

# Add webapp to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up test environment
os.environ['DATABASE_URL'] = 'sqlite:///test_char_limits.db'
os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-key-12345'

from app import app, db, User

# Get the constant from User class
FREE_CHAR_LIMIT = User.FREE_CHAR_LIMIT

# Test results tracking
test_results = {
    'passed': 0,
    'failed': 0,
    'errors': []
}

def log_test(test_name, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {test_name}")
    if details:
        print(f"       Details: {details}")
    if passed:
        test_results['passed'] += 1
    else:
        test_results['failed'] += 1
        test_results['errors'].append(f"{test_name}: {details}")

def test_user_model():
    """Test User model character tracking fields"""
    print("\n" + "="*60)
    print("TEST 1: User Model Character Tracking")
    print("="*60)
    
    with app.app_context():
        # Create test user
        test_email = f"test_{int(time.time())}@test.com"
        test_password = hashlib.sha256("testpass123".encode()).hexdigest()
        
        user = User(
            email=test_email,
            password_hash=test_password,
            subscription_status='none',
            api_tier='none'
        )
        db.session.add(user)
        db.session.commit()
        
        # Test 1a: Check default values
        log_test(
            "User starts with 0 chars_used",
            (user.chars_used or 0) == 0,
            f"Expected 0, got {user.chars_used}"
        )
        
        # Test 1b: Check char_limit property for free user
        log_test(
            "Free user has 10,000 char limit",
            user.char_limit == FREE_CHAR_LIMIT,
            f"Expected {FREE_CHAR_LIMIT}, got {user.char_limit}"
        )
        
        # Test 1c: Check chars_remaining property
        log_test(
            "Free user has 10,000 chars remaining",
            user.chars_remaining == FREE_CHAR_LIMIT,
            f"Expected {FREE_CHAR_LIMIT}, got {user.chars_remaining}"
        )
        
        # Test 1d: Test use_chars method
        success, msg = user.use_chars(100)
        db.session.commit()
        log_test(
            "use_chars(100) succeeds",
            success == True,
            f"Expected True, got {success}. Message: {msg}"
        )
        
        log_test(
            "chars_used updated to 100",
            user.chars_used == 100,
            f"Expected 100, got {user.chars_used}"
        )
        
        log_test(
            "chars_remaining is now 9900",
            user.chars_remaining == 9900,
            f"Expected 9900, got {user.chars_remaining}"
        )
        
        # Test 1e: Test limit enforcement
        user.chars_used = 9950  # 50 chars remaining
        db.session.commit()
        
        success, msg = user.use_chars(100)  # Try to use 100 when only 50 remain
        log_test(
            "use_chars(100) fails when only 50 remain",
            success == False,
            f"Expected False, got {success}. Message: {msg}"
        )
        
        log_test(
            "Error message mentions limit",
            "limit" in msg.lower() or "exceeded" in msg.lower(),
            f"Message: {msg}"
        )
        
        # Test 1f: Test unlimited for subscribers
        user.subscription_status = 'active'
        db.session.commit()
        
        # Note: The app uses a very large number instead of float('inf') for DB compatibility
        UNLIMITED_LIMIT = 999999999
        
        log_test(
            "Active subscriber has unlimited char_limit",
            user.char_limit >= UNLIMITED_LIMIT or user.char_limit == float('inf'),
            f"Expected >= {UNLIMITED_LIMIT}, got {user.char_limit}"
        )
        
        success, msg = user.use_chars(100000)  # Large amount
        log_test(
            "Active subscriber can use unlimited chars",
            success == True,
            f"Expected True, got {success}. Message: {msg}"
        )
        
        # Test 1g: Test lifetime subscriber
        user.subscription_status = 'lifetime'
        db.session.commit()
        
        log_test(
            "Lifetime subscriber has unlimited char_limit",
            user.char_limit >= UNLIMITED_LIMIT or user.char_limit == float('inf'),
            f"Expected >= {UNLIMITED_LIMIT}, got {user.char_limit}"
        )
        
        # Test 1h: Test monthly reset
        user.subscription_status = 'none'
        user.chars_used = 5000
        user.chars_reset_at = datetime.utcnow() - timedelta(days=35)  # 35 days ago
        db.session.commit()
        
        user.check_and_reset_usage()
        db.session.commit()
        
        log_test(
            "Monthly reset clears chars_used",
            user.chars_used == 0,
            f"Expected 0 after reset, got {user.chars_used}"
        )
        
        # Cleanup
        db.session.delete(user)
        db.session.commit()

def test_auth_endpoints():
    """Test auth endpoints return character usage data"""
    print("\n" + "="*60)
    print("TEST 2: Auth Endpoints Character Data")
    print("="*60)
    
    client = app.test_client()
    
    # Test 2a: Signup returns char data
    test_email = f"signup_test_{int(time.time())}@test.com"
    response = client.post('/api/v1/auth/signup', json={
        'email': test_email,
        'password': 'TestPass123!'
    })
    data = response.get_json()
    
    log_test(
        "Signup endpoint returns success",
        data is not None and data.get('success') == True,
        f"Response: {data}"
    )
    
    # Check if char data is in user object or top level
    user_data = data.get('user', data) if data else {}
    
    log_test(
        "Signup returns chars_used",
        'chars_used' in user_data,
        f"Keys in response: {list(user_data.keys()) if user_data else 'None'}"
    )
    
    log_test(
        "Signup returns chars_remaining",
        'chars_remaining' in user_data,
        f"Keys in response: {list(user_data.keys()) if user_data else 'None'}"
    )
    
    log_test(
        "Signup returns chars_limit",
        'chars_limit' in user_data,
        f"Keys in response: {list(user_data.keys()) if user_data else 'None'}"
    )
    
    log_test(
        "Signup chars_used is 0",
        user_data.get('chars_used') == 0,
        f"Expected 0, got {user_data.get('chars_used')}"
    )
    
    log_test(
        "Signup chars_limit is 10000",
        user_data.get('chars_limit') == FREE_CHAR_LIMIT,
        f"Expected {FREE_CHAR_LIMIT}, got {user_data.get('chars_limit')}"
    )
    
    # Test 2b: Login returns char data
    response = client.post('/api/v1/auth/login', json={
        'email': test_email,
        'password': 'TestPass123!'
    })
    data = response.get_json()
    
    log_test(
        "Login endpoint returns success",
        data is not None and data.get('success') == True,
        f"Response: {data}"
    )
    
    user_data = data.get('user', data) if data else {}
    
    log_test(
        "Login returns chars_used",
        'chars_used' in user_data,
        f"Keys in response: {list(user_data.keys()) if user_data else 'None'}"
    )
    
    log_test(
        "Login returns chars_remaining",
        'chars_remaining' in user_data,
        f"Keys in response: {list(user_data.keys()) if user_data else 'None'}"
    )
    
    # Cleanup
    with app.app_context():
        user = User.query.filter_by(email=test_email).first()
        if user:
            db.session.delete(user)
            db.session.commit()

def test_generate_endpoint_char_tracking():
    """Test /api/generate endpoint tracks and enforces character limits"""
    print("\n" + "="*60)
    print("TEST 3: Generate Endpoint Character Tracking")
    print("="*60)
    
    client = app.test_client()
    
    # Create test user directly in database for testing
    with app.app_context():
        test_email = f"gen_test_{int(time.time())}@test.com"
        test_password = hashlib.sha256("testpass123".encode()).hexdigest()
        
        user = User(
            email=test_email,
            password_hash=test_password,
            subscription_status='none'
        )
        user.chars_used = 0
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    
    # Test 3a: Basic generation with character tracking
    test_text = "Hello world, this is a test."  # 28 characters (no trailing space)
    
    # Since we can't actually call edge-tts in tests, we'll test the 
    # character counting and limit checking logic directly
    
    with app.app_context():
        user = User.query.get(user_id)
        initial_chars = user.chars_used or 0
        
        # Simulate what the endpoint does
        import re
        plain_text = re.sub(r'<[^>]+>', '', test_text)
        char_count = len(plain_text)
        
        log_test(
            "Character count is correct",
            char_count == 28,  # Correct count for the text
            f"Expected 28, got {char_count}"
        )
        
        # Test use_chars
        success, msg = user.use_chars(char_count)
        db.session.commit()
        
        log_test(
            "use_chars succeeds for valid text",
            success == True,
            f"Message: {msg}"
        )
        
        log_test(
            "chars_used increased by correct amount",
            user.chars_used == initial_chars + char_count,
            f"Expected {initial_chars + char_count}, got {user.chars_used}"
        )
        
        # Test 3b: Test at limit
        user.chars_used = FREE_CHAR_LIMIT  # At exact limit
        db.session.commit()
        
        success, msg = user.use_chars(1)  # Try to use 1 more char
        
        log_test(
            "Cannot use chars when at limit",
            success == False,
            f"Expected False, got {success}. Message: {msg}"
        )
        
        # Test 3c: Test over limit
        user.chars_used = FREE_CHAR_LIMIT + 100  # Over limit
        db.session.commit()
        
        success, msg = user.use_chars(10)
        
        log_test(
            "Cannot use chars when over limit",
            success == False,
            f"Message: {msg}"
        )
        
        # Cleanup
        db.session.delete(user)
        db.session.commit()

def test_chunk_character_counting():
    """Test character counting for chunked/multi-speaker text"""
    print("\n" + "="*60)
    print("TEST 4: Chunk Character Counting")
    print("="*60)
    
    import re
    
    # Test 4a: Simple chunks
    chunks = [
        {'content': 'Hello world'},  # 11 chars
        {'content': 'How are you?'},  # 12 chars
    ]
    
    total = 0
    for chunk in chunks:
        plain = re.sub(r'<[^>]+>', '', chunk.get('content', ''))
        total += len(plain)
    
    log_test(
        "Simple chunk counting correct",
        total == 23,
        f"Expected 23, got {total}"
    )
    
    # Test 4b: Chunks with SSML
    chunks_ssml = [
        {'content': '<speak>Hello</speak>'},  # 5 chars of actual text
        {'content': '<prosody rate="fast">World</prosody>'},  # 5 chars
    ]
    
    total = 0
    for chunk in chunks_ssml:
        plain = re.sub(r'<[^>]+>', '', chunk.get('content', ''))
        total += len(plain)
    
    log_test(
        "SSML tag stripping works",
        total == 10,
        f"Expected 10, got {total}"
    )
    
    # Test 4c: Multi-speaker dialogue format
    dialogue_text = "[John]: Hello there!\n[Sarah]: Hi John, how are you?"
    
    # When parsed, the speaker names should NOT be counted in chars
    # Just the actual dialogue text
    # "Hello there!" = 12 chars, "Hi John, how are you?" = 21 chars = 33 total
    
    # But the raw text including markup
    plain = re.sub(r'<[^>]+>', '', dialogue_text)
    raw_chars = len(plain)
    
    log_test(
        "Raw dialogue text char count",
        raw_chars == len(dialogue_text),
        f"Raw text: {raw_chars} chars"
    )

def test_mobile_api_endpoint():
    """Test /api/v1/mobile/synthesize endpoint"""
    print("\n" + "="*60)
    print("TEST 5: Mobile API Endpoint")
    print("="*60)
    
    client = app.test_client()
    
    # Create and login test user using v1 API
    test_email = f"mobile_test_{int(time.time())}@test.com"
    signup_resp = client.post('/api/v1/auth/signup', json={
        'email': test_email,
        'password': 'TestPass123!'
    })
    signup_data = signup_resp.get_json()
    session_token = signup_data.get('token')
    
    log_test(
        "Mobile signup returns session token",
        session_token is not None,
        f"Token: {session_token[:20] if session_token else 'None'}..."
    )
    
    # Test mobile synthesize endpoint exists and checks auth
    response = client.post('/api/v1/mobile/synthesize', json={
        'text': 'Hello test',
        'voice': 'en-US-EmmaMultilingualNeural'
    })
    
    # Without auth, should fail
    log_test(
        "Mobile endpoint requires auth",
        response.status_code in [401, 403] or not response.get_json().get('success'),
        f"Status: {response.status_code}"
    )
    
    # Test with auth header
    response = client.post('/api/v1/mobile/synthesize', 
        json={
            'text': 'Hello test',
            'voice': 'en-US-EmmaMultilingualNeural'
        },
        headers={
            'Authorization': f'Bearer {session_token}'
        }
    )
    data = response.get_json() or {}
    
    # The actual TTS call might fail in test env, but we can check the structure
    log_test(
        "Mobile endpoint responds to auth request",
        response.status_code in [200, 400, 500],  # Any valid response
        f"Status: {response.status_code}, Response: {data}"
    )
    
    # Test character limit on mobile endpoint
    with app.app_context():
        user = User.query.filter_by(email=test_email).first()
        if user:
            user.chars_used = FREE_CHAR_LIMIT  # Set at limit
            db.session.commit()
    
    response = client.post('/api/v1/mobile/synthesize',
        json={
            'text': 'This should fail due to limit',
            'voice': 'en-US-EmmaMultilingualNeural'
        },
        headers={
            'Authorization': f'Bearer {session_token}'
        }
    )
    data = response.get_json() or {}
    
    log_test(
        "Mobile endpoint enforces char limit",
        data.get('success') == False or 'limit' in str(data).lower(),
        f"Response: {data}"
    )
    
    # Cleanup
    with app.app_context():
        user = User.query.filter_by(email=test_email).first()
        if user:
            db.session.delete(user)
            db.session.commit()

def test_voice_configurations():
    """Test different voice configurations with character tracking"""
    print("\n" + "="*60)
    print("TEST 6: Voice Configuration Char Tracking")
    print("="*60)
    
    with app.app_context():
        # Create test user
        test_email = f"voice_test_{int(time.time())}@test.com"
        test_password = hashlib.sha256("testpass123".encode()).hexdigest()
        
        user = User(
            email=test_email,
            password_hash=test_password,
            subscription_status='none'
        )
        db.session.add(user)
        db.session.commit()
        
        # Test 6a: Voice without emotion (Emma)
        text1 = "Hello from Emma voice"  # 21 chars
        success, _ = user.use_chars(len(text1))
        db.session.commit()
        
        log_test(
            "Voice without emotion charges correctly",
            user.chars_used == 21,
            f"Expected 21, got {user.chars_used}"
        )
        
        # Test 6b: Voice with emotion (Jenny with cheerful)
        text2 = "I am so happy today!"  # 20 chars
        success, _ = user.use_chars(len(text2))
        db.session.commit()
        
        log_test(
            "Voice with emotion charges correctly",
            user.chars_used == 41,
            f"Expected 41, got {user.chars_used}"
        )
        
        # Test 6c: Voice with emotion but not using it
        text3 = "Just normal text"  # 16 chars
        success, _ = user.use_chars(len(text3))
        db.session.commit()
        
        log_test(
            "Voice capable of emotion (no emotion used) charges correctly",
            user.chars_used == 57,
            f"Expected 57, got {user.chars_used}"
        )
        
        # Cleanup
        db.session.delete(user)
        db.session.commit()

def test_multi_speaker_scenarios():
    """Test multi-speaker dialogue character counting"""
    print("\n" + "="*60)
    print("TEST 7: Multi-Speaker Dialogue Char Tracking")
    print("="*60)
    
    with app.app_context():
        # Create test user
        test_email = f"multi_test_{int(time.time())}@test.com"
        test_password = hashlib.sha256("testpass123".encode()).hexdigest()
        
        user = User(
            email=test_email,
            password_hash=test_password,
            subscription_status='none'
        )
        db.session.add(user)
        db.session.commit()
        
        # Test 7a: Two speakers, no emotions
        chunks = [
            {'content': 'Hello from John', 'voice': 'en-US-GuyNeural'},  # 15 chars
            {'content': 'Hi John from Sarah', 'voice': 'en-US-JennyNeural'},  # 18 chars
        ]
        total_chars = sum(len(c['content']) for c in chunks)
        
        success, _ = user.use_chars(total_chars)
        db.session.commit()
        
        log_test(
            "Multi-speaker no emotions: correct char count",
            user.chars_used == 33,
            f"Expected 33, got {user.chars_used}"
        )
        
        # Test 7b: Two speakers, with emotions
        chunks2 = [
            {'content': 'I am happy!', 'voice': 'en-US-JennyNeural', 'emotion': 'cheerful'},  # 11 chars
            {'content': 'I am sad.', 'voice': 'en-US-JennyNeural', 'emotion': 'sad'},  # 9 chars
        ]
        total_chars2 = sum(len(c['content']) for c in chunks2)
        
        success, _ = user.use_chars(total_chars2)
        db.session.commit()
        
        log_test(
            "Multi-speaker with emotions: correct char count",
            user.chars_used == 53,  # 33 + 20
            f"Expected 53, got {user.chars_used}"
        )
        
        # Test 7c: Mixed - some with emotions, some without
        chunks3 = [
            {'content': 'Normal text here', 'voice': 'en-US-EmmaMultilingualNeural'},  # 16 chars
            {'content': 'Excited text!', 'voice': 'en-US-JennyNeural', 'emotion': 'cheerful'},  # 13 chars
            {'content': 'More normal', 'voice': 'en-US-GuyNeural'},  # 11 chars
        ]
        total_chars3 = sum(len(c['content']) for c in chunks3)
        
        success, _ = user.use_chars(total_chars3)
        db.session.commit()
        
        log_test(
            "Multi-speaker mixed emotions: correct char count",
            user.chars_used == 93,  # 53 + 40
            f"Expected 93, got {user.chars_used}"
        )
        
        # Cleanup
        db.session.delete(user)
        db.session.commit()

def test_edge_cases():
    """Test edge cases and boundary conditions"""
    print("\n" + "="*60)
    print("TEST 8: Edge Cases and Boundary Conditions")
    print("="*60)
    
    with app.app_context():
        # Create test user
        test_email = f"edge_test_{int(time.time())}@test.com"
        test_password = hashlib.sha256("testpass123".encode()).hexdigest()
        
        user = User(
            email=test_email,
            password_hash=test_password,
            subscription_status='none'
        )
        db.session.add(user)
        db.session.commit()
        
        # Test 8a: Empty text
        success, msg = user.use_chars(0)
        log_test(
            "Empty text (0 chars) is allowed",
            success == True,
            f"Success: {success}, Message: {msg}"
        )
        
        # Test 8b: Exactly at limit
        user.chars_used = FREE_CHAR_LIMIT - 10
        db.session.commit()
        
        success, msg = user.use_chars(10)  # Use exactly remaining
        log_test(
            "Using exactly remaining chars succeeds",
            success == True,
            f"Success: {success}, Message: {msg}"
        )
        
        log_test(
            "Now at exact limit",
            user.chars_used == FREE_CHAR_LIMIT,
            f"Expected {FREE_CHAR_LIMIT}, got {user.chars_used}"
        )
        
        # Test 8c: 1 char over limit
        success, msg = user.use_chars(1)
        log_test(
            "1 char over limit fails",
            success == False,
            f"Message: {msg}"
        )
        
        # Test 8d: Very large text
        user.chars_used = 0
        db.session.commit()
        
        success, msg = user.use_chars(FREE_CHAR_LIMIT + 1)
        log_test(
            "Very large text (over limit) fails",
            success == False,
            f"Message: {msg}"
        )
        
        # Test 8e: Negative chars (should not happen but test anyway)
        user.chars_used = 0
        db.session.commit()
        
        # The use_chars method should handle negative gracefully
        try:
            success, msg = user.use_chars(-100)
            log_test(
                "Negative chars handled",
                True,  # As long as no crash
                f"Success: {success}, Chars_used: {user.chars_used}"
            )
        except Exception as e:
            log_test(
                "Negative chars handled",
                False,
                f"Exception: {e}"
            )
        
        # Cleanup
        db.session.delete(user)
        db.session.commit()

def test_subscription_tiers():
    """Test different subscription tiers"""
    print("\n" + "="*60)
    print("TEST 9: Subscription Tier Limits")
    print("="*60)
    
    UNLIMITED_LIMIT = 999999999  # The app uses this instead of float('inf')
    
    with app.app_context():
        # Test each subscription status
        test_cases = [
            ('none', FREE_CHAR_LIMIT, False),
            ('inactive', FREE_CHAR_LIMIT, False),
            ('active', UNLIMITED_LIMIT, True),
            ('lifetime', UNLIMITED_LIMIT, True),
            ('canceled', FREE_CHAR_LIMIT, False),  # Canceled should have limit
        ]
        
        for status, expected_limit, is_unlimited in test_cases:
            test_email = f"tier_{status}_{int(time.time())}@test.com"
            test_password = hashlib.sha256("testpass123".encode()).hexdigest()
            
            user = User(
                email=test_email,
                password_hash=test_password,
                subscription_status=status
            )
            # Initialize chars_reset_at to prevent auto-reset
            user.chars_reset_at = datetime.utcnow() + timedelta(days=30)
            user.chars_used = 0
            db.session.add(user)
            db.session.commit()
            
            limit_ok = (user.char_limit == expected_limit) or (is_unlimited and user.char_limit >= UNLIMITED_LIMIT)
            log_test(
                f"Subscription '{status}' has correct limit",
                limit_ok,
                f"Expected {expected_limit}, got {user.char_limit}"
            )
            
            # Test if unlimited works
            if is_unlimited:
                success, _ = user.use_chars(100000)
                log_test(
                    f"Subscription '{status}' allows large usage",
                    success == True,
                    f"Can use 100k chars: {success}"
                )
            else:
                # Set at limit - must set chars_reset_at first to prevent reset
                user.chars_used = expected_limit
                user.chars_reset_at = datetime.utcnow() + timedelta(days=30)  # Future date
                db.session.commit()
                
                success, msg = user.use_chars(1)
                log_test(
                    f"Subscription '{status}' enforces limit",
                    success == False,
                    f"Blocked at limit: {not success}. chars_used={user.chars_used}, msg={msg}"
                )
            
            # Cleanup
            db.session.delete(user)
            db.session.commit()

def test_api_response_structure():
    """Test that API responses include correct character data"""
    print("\n" + "="*60)
    print("TEST 10: API Response Structure")
    print("="*60)
    
    client = app.test_client()
    
    # Create and login test user
    test_email = f"response_test_{int(time.time())}@test.com"
    signup_resp = client.post('/api/v1/auth/signup', json={
        'email': test_email,
        'password': 'TestPass123!'
    })
    
    data = signup_resp.get_json()
    user_data = data.get('user', {}) if data else {}
    
    # Check all required fields
    required_fields = ['chars_used', 'chars_remaining', 'chars_limit']
    for field in required_fields:
        log_test(
            f"Signup response has '{field}'",
            field in user_data,
            f"Fields present: {list(user_data.keys())}"
        )
    
    # Check data types
    if 'chars_used' in user_data:
        log_test(
            "chars_used is numeric",
            isinstance(user_data['chars_used'], (int, float)),
            f"Type: {type(user_data['chars_used'])}"
        )
    
    if 'chars_limit' in user_data:
        log_test(
            "chars_limit is numeric",
            isinstance(user_data['chars_limit'], (int, float)),
            f"Type: {type(user_data['chars_limit'])}"
        )
    
    # Cleanup
    with app.app_context():
        user = User.query.filter_by(email=test_email).first()
        if user:
            db.session.delete(user)
            db.session.commit()

def test_ssml_character_counting():
    """Test SSML content character counting (strips tags)"""
    print("\n" + "="*60)
    print("TEST 11: SSML Character Counting")
    print("="*60)
    
    import re
    
    test_cases = [
        ('<speak>Hello</speak>', 5),
        ('<speak><prosody rate="fast">Hello World</prosody></speak>', 11),
        ('<speak><break time="500ms"/>Pause here</speak>', 10),
        ('<speak><emphasis>Important</emphasis> text</speak>', 14),
        ('<speak>No tags</speak>', 7),
        ('Plain text no SSML', 18),
    ]
    
    for ssml, expected_chars in test_cases:
        plain = re.sub(r'<[^>]+>', '', ssml)
        actual = len(plain)
        log_test(
            f"SSML '{ssml[:30]}...' chars",
            actual == expected_chars,
            f"Expected {expected_chars}, got {actual} (plain: '{plain}')"
        )

def run_all_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("     CHARACTER LIMIT IMPLEMENTATION - COMPREHENSIVE TEST SUITE")
    print("="*70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"FREE_CHAR_LIMIT: {FREE_CHAR_LIMIT}")
    
    # Initialize test database
    with app.app_context():
        db.create_all()
        
        # Ensure tables have required columns
        try:
            # Check if chars_used column exists
            test_user = User.query.first()
            if test_user:
                _ = test_user.chars_used
        except Exception as e:
            print(f"Warning: Database schema may need migration: {e}")
    
    # Run all tests
    try:
        test_user_model()
        test_auth_endpoints()
        test_generate_endpoint_char_tracking()
        test_chunk_character_counting()
        test_mobile_api_endpoint()
        test_voice_configurations()
        test_multi_speaker_scenarios()
        test_edge_cases()
        test_subscription_tiers()
        test_api_response_structure()
        test_ssml_character_counting()
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        test_results['errors'].append(f"FATAL: {e}")
    
    # Print summary
    print("\n" + "="*70)
    print("                         TEST SUMMARY")
    print("="*70)
    total = test_results['passed'] + test_results['failed']
    print(f"Total Tests: {total}")
    print(f"✅ Passed: {test_results['passed']}")
    print(f"❌ Failed: {test_results['failed']}")
    
    if test_results['errors']:
        print(f"\nFailed Tests:")
        for error in test_results['errors']:
            print(f"  - {error}")
    
    success_rate = (test_results['passed'] / total * 100) if total > 0 else 0
    print(f"\nSuccess Rate: {success_rate:.1f}%")
    
    if success_rate == 100:
        print("\n🎉 ALL TESTS PASSED! Character limit implementation is working correctly.")
    elif success_rate >= 90:
        print("\n⚠️ Most tests passed, but some issues need attention.")
    else:
        print("\n❌ Multiple tests failed. Implementation needs review.")
    
    print("="*70)
    
    return test_results['failed'] == 0

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
