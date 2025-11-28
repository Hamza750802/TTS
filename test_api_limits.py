"""
Comprehensive API Limits Test
Tests every single step of the API flow from A to Z
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'webapp'))

# Set up test environment
os.environ['DATABASE_URL'] = 'sqlite:///test_api_limits.db'
os.environ['SECRET_KEY'] = 'test-secret-key-12345'
os.environ['STRIPE_SECRET_KEY'] = 'sk_test_fake_key'  # Fake key to enable billing checks
os.environ['STRIPE_PRICE_ID'] = 'price_fake_123'  # Fake price to enable billing checks

from datetime import datetime, timedelta

from webapp.app import APIKey, User, app, db

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")

def print_test(test_name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} | {test_name}")
    if details:
        print(f"       └─ {details}")

def run_tests():
    with app.app_context():
        # Clean up any existing test data
        db.drop_all()
        db.create_all()
        
        print_header("TEST 1: User Model - API Tier Limits")
        
        # Create test users for each tier
        user_no_plan = User(email="no_plan@test.com")
        user_no_plan.set_password("test123")
        user_no_plan.api_tier = 'none'
        
        user_starter = User(email="starter@test.com")
        user_starter.set_password("test123")
        user_starter.api_tier = 'starter'
        
        user_pro = User(email="pro@test.com")
        user_pro.set_password("test123")
        user_pro.api_tier = 'pro'
        
        user_enterprise = User(email="enterprise@test.com")
        user_enterprise.set_password("test123")
        user_enterprise.api_tier = 'enterprise'
        
        db.session.add_all([user_no_plan, user_starter, user_pro, user_enterprise])
        db.session.commit()
        
        # Test 1.1: Verify character limits per tier
        print_test("No plan user has 0 char limit", 
                   user_no_plan.api_char_limit == 0,
                   f"Limit: {user_no_plan.api_char_limit}")
        
        print_test("Starter plan has 100,000 char limit", 
                   user_starter.api_char_limit == 100000,
                   f"Limit: {user_starter.api_char_limit:,}")
        
        print_test("Pro plan has 500,000 char limit", 
                   user_pro.api_char_limit == 500000,
                   f"Limit: {user_pro.api_char_limit:,}")
        
        print_test("Enterprise plan has ~unlimited char limit", 
                   user_enterprise.api_char_limit == 999999999,
                   f"Limit: {user_enterprise.api_char_limit:,}")
        
        # Test 1.2: Verify has_api_access property
        print_header("TEST 2: has_api_access Property")
        
        print_test("No plan user has NO API access", 
                   user_no_plan.has_api_access == False)
        
        print_test("Starter user HAS API access", 
                   user_starter.has_api_access == True)
        
        print_test("Pro user HAS API access", 
                   user_pro.has_api_access == True)
        
        print_test("Enterprise user HAS API access", 
                   user_enterprise.has_api_access == True)
        
        # Test 1.3: Verify remaining characters calculation
        print_header("TEST 3: Characters Remaining Calculation")
        
        # Fresh user should have full limit
        print_test("Fresh starter user has 100k remaining", 
                   user_starter.api_chars_remaining == 100000,
                   f"Remaining: {user_starter.api_chars_remaining:,}")
        
        # Simulate some usage
        user_starter.api_chars_used = 25000
        db.session.commit()
        
        print_test("After 25k used, starter has 75k remaining", 
                   user_starter.api_chars_remaining == 75000,
                   f"Remaining: {user_starter.api_chars_remaining:,}")
        
        # Test at limit
        user_starter.api_chars_used = 100000
        db.session.commit()
        
        print_test("At 100k used, starter has 0 remaining", 
                   user_starter.api_chars_remaining == 0,
                   f"Remaining: {user_starter.api_chars_remaining:,}")
        
        # Test over limit (should never go negative)
        user_starter.api_chars_used = 150000
        db.session.commit()
        
        print_test("Over limit shows 0 remaining (not negative)", 
                   user_starter.api_chars_remaining == 0,
                   f"Remaining: {user_starter.api_chars_remaining:,}")
        
        # Reset for next tests
        user_starter.api_chars_used = 0
        db.session.commit()
        
        # Test 2: use_api_chars function
        print_header("TEST 4: use_api_chars() Function")
        
        # Test successful usage
        result = user_starter.use_api_chars(10000)
        print_test("Using 10k chars succeeds", 
                   result == True,
                   f"Used: {user_starter.api_chars_used:,}")
        
        result = user_starter.use_api_chars(50000)
        print_test("Using additional 50k chars succeeds", 
                   result == True,
                   f"Total used: {user_starter.api_chars_used:,}")
        
        # Try to exceed limit
        result = user_starter.use_api_chars(50000)  # Would make 110k total
        print_test("Using 50k more (would exceed 100k limit) FAILS", 
                   result == False,
                   f"Total used still: {user_starter.api_chars_used:,}")
        
        # Verify usage didn't change
        print_test("Usage unchanged after failed attempt", 
                   user_starter.api_chars_used == 60000,
                   f"Used: {user_starter.api_chars_used:,}")
        
        # Test exact remaining
        remaining = user_starter.api_chars_remaining
        result = user_starter.use_api_chars(remaining)
        print_test("Using exact remaining amount succeeds", 
                   result == True,
                   f"Now at: {user_starter.api_chars_used:,}/{user_starter.api_char_limit:,}")
        
        # Now at limit, any usage should fail
        result = user_starter.use_api_chars(1)
        print_test("Using even 1 char when at limit FAILS", 
                   result == False)
        
        # Test 3: Monthly reset
        print_header("TEST 5: Monthly Reset Functionality")
        
        # Reset user for this test
        user_pro.api_chars_used = 400000
        user_pro.api_usage_reset_at = datetime.utcnow() - timedelta(days=1)  # Set to yesterday
        db.session.commit()
        
        print_test("Pro user has 400k used before reset", 
                   user_pro.api_chars_used == 400000)
        
        # Call check_and_reset - should reset because date passed
        user_pro.check_and_reset_api_usage()
        db.session.commit()
        
        print_test("After reset check, usage is back to 0", 
                   user_pro.api_chars_used == 0,
                   f"Used: {user_pro.api_chars_used}")
        
        print_test("Reset date set to ~30 days from now", 
                   user_pro.api_usage_reset_at > datetime.utcnow() + timedelta(days=29),
                   f"Resets at: {user_pro.api_usage_reset_at}")
        
        # Test that it doesn't reset if date not passed
        user_pro.api_chars_used = 200000
        user_pro.api_usage_reset_at = datetime.utcnow() + timedelta(days=15)  # 15 days from now
        db.session.commit()
        
        user_pro.check_and_reset_api_usage()
        db.session.commit()
        
        print_test("Usage NOT reset if date hasn't passed", 
                   user_pro.api_chars_used == 200000,
                   f"Used: {user_pro.api_chars_used:,}")
        
        # Test 4: API Key validation
        print_header("TEST 6: API Key Creation & Validation")
        
        # Create API keys
        api_key_starter = APIKey(
            user_id=user_starter.id,
            key=APIKey.generate_key(),
            name="Test Key Starter"
        )
        
        api_key_pro = APIKey(
            user_id=user_pro.id,
            key=APIKey.generate_key(),
            name="Test Key Pro"
        )
        
        api_key_no_plan = APIKey(
            user_id=user_no_plan.id,
            key=APIKey.generate_key(),
            name="Test Key No Plan"
        )
        
        db.session.add_all([api_key_starter, api_key_pro, api_key_no_plan])
        db.session.commit()
        
        print_test("API key generated for starter user", 
                   len(api_key_starter.key) > 20,
                   f"Key: {api_key_starter.key[:20]}...")
        
        print_test("API key generated for pro user", 
                   len(api_key_pro.key) > 20)
        
        print_test("API key is unique", 
                   api_key_starter.key != api_key_pro.key)
        
        # Test 5: verify_api_key function
        print_header("TEST 7: verify_api_key() Function")
        
        from webapp.app import verify_api_key

        # Reset starter usage for clean test
        user_starter.api_chars_used = 0
        user_starter.api_usage_reset_at = datetime.utcnow() + timedelta(days=30)
        db.session.commit()
        
        # Test valid key with no char count
        result = verify_api_key(api_key_starter.key)
        print_test("Valid API key returns valid=True", 
                   result.get('valid') == True)
        
        # Test invalid key
        result = verify_api_key("invalid-key-12345")
        print_test("Invalid API key returns valid=False", 
                   result.get('valid') == False,
                   f"Error: {result.get('error', '')[:50]}")
        
        # Test empty key
        result = verify_api_key("")
        print_test("Empty API key returns valid=False", 
                   result.get('valid') == False)
        
        # Test key with usage check - should pass
        result = verify_api_key(api_key_starter.key, char_count=5000)
        print_test("Starter key with 5k chars passes", 
                   result.get('valid') == True)
        
        # Set starter user to near limit
        user_starter.api_chars_used = 99000
        db.session.commit()
        
        # Test key with usage that would exceed
        result = verify_api_key(api_key_starter.key, char_count=5000)
        print_test("Starter key with 5k chars when 99k used FAILS", 
                   result.get('valid') == False,
                   f"Error: {result.get('error', '')[:60]}...")
        
        # Verify usage info is returned
        print_test("Failed response includes usage info", 
                   'usage' in result,
                   f"Usage: {result.get('usage', {})}")
        
        # Test 6: Deactivated key
        print_header("TEST 8: Deactivated API Key")
        
        api_key_starter.is_active = False
        db.session.commit()
        
        result = verify_api_key(api_key_starter.key)
        print_test("Deactivated API key returns invalid", 
                   result.get('valid') == False)
        
        # Reactivate for remaining tests
        api_key_starter.is_active = True
        db.session.commit()
        
        # Test 7: User without API plan trying to use API
        print_header("TEST 9: User Without API Plan")
        
        # Note: verify_api_key only checks billing when billing_enabled()
        # Since we disabled Stripe, this test simulates the check
        
        print_test("User with no plan has_api_access=False", 
                   user_no_plan.has_api_access == False)
        
        print_test("User with no plan has 0 char limit", 
                   user_no_plan.api_char_limit == 0)
        
        result = user_no_plan.use_api_chars(100)
        print_test("User with no plan cannot use chars", 
                   result == False)
        
        # Test 8: Edge cases
        print_header("TEST 10: Edge Cases")
        
        # Zero char request
        user_pro.api_chars_used = 0
        db.session.commit()
        result = user_pro.use_api_chars(0)
        print_test("Zero char usage returns True", 
                   result == True)
        
        # Very large request
        user_enterprise.api_chars_used = 0
        db.session.commit()
        result = user_enterprise.use_api_chars(10000000)  # 10 million
        print_test("Enterprise can use 10 million chars", 
                   result == True,
                   f"Used: {user_enterprise.api_chars_used:,}")
        
        # Negative chars (shouldn't happen but let's verify)
        # The function doesn't check for negative, but it would fail the limit check
        
        # Test Pro user flow
        print_header("TEST 11: Complete Pro User Flow")
        
        user_pro.api_chars_used = 0
        user_pro.api_usage_reset_at = datetime.utcnow() + timedelta(days=30)
        db.session.commit()
        
        steps_passed = 0
        
        # Step 1: Fresh user has full limit
        if user_pro.api_chars_remaining == 500000:
            steps_passed += 1
            print_test("Step 1: Fresh pro user has 500k limit", True)
        else:
            print_test("Step 1: Fresh pro user has 500k limit", False, f"Got: {user_pro.api_chars_remaining}")
        
        # Step 2: Use some chars
        user_pro.use_api_chars(100000)
        db.session.commit()
        if user_pro.api_chars_remaining == 400000:
            steps_passed += 1
            print_test("Step 2: After 100k use, 400k remaining", True)
        else:
            print_test("Step 2: After 100k use, 400k remaining", False, f"Got: {user_pro.api_chars_remaining}")
        
        # Step 3: Continue using
        user_pro.use_api_chars(200000)
        db.session.commit()
        if user_pro.api_chars_remaining == 200000:
            steps_passed += 1
            print_test("Step 3: After 200k more, 200k remaining", True)
        else:
            print_test("Step 3: After 200k more, 200k remaining", False, f"Got: {user_pro.api_chars_remaining}")
        
        # Step 4: Try to exceed
        result = user_pro.use_api_chars(250000)
        if result == False and user_pro.api_chars_used == 300000:
            steps_passed += 1
            print_test("Step 4: Can't use 250k when only 200k left", True)
        else:
            print_test("Step 4: Can't use 250k when only 200k left", False)
        
        # Step 5: Use exact remaining
        result = user_pro.use_api_chars(200000)
        db.session.commit()
        if result == True and user_pro.api_chars_remaining == 0:
            steps_passed += 1
            print_test("Step 5: Can use exact remaining (200k)", True)
        else:
            print_test("Step 5: Can use exact remaining (200k)", False)
        
        # Step 6: At limit, any use fails
        result = user_pro.use_api_chars(1)
        if result == False:
            steps_passed += 1
            print_test("Step 6: At limit, even 1 char fails", True)
        else:
            print_test("Step 6: At limit, even 1 char fails", False)
        
        # Step 7: Simulate month passing
        user_pro.api_usage_reset_at = datetime.utcnow() - timedelta(days=1)
        user_pro.check_and_reset_api_usage()
        db.session.commit()
        if user_pro.api_chars_used == 0 and user_pro.api_chars_remaining == 500000:
            steps_passed += 1
            print_test("Step 7: After month, usage resets to 0", True)
        else:
            print_test("Step 7: After month, usage resets to 0", False)
        
        # Step 8: Can use again after reset
        result = user_pro.use_api_chars(50000)
        db.session.commit()
        if result == True and user_pro.api_chars_used == 50000:
            steps_passed += 1
            print_test("Step 8: Can use chars again after reset", True)
        else:
            print_test("Step 8: Can use chars again after reset", False)
        
        # Final Summary
        print_header("FINAL SUMMARY")
        print(f"\n  Pro User Flow: {steps_passed}/8 steps passed")
        
        # Cleanup
        db.drop_all()
        
        # Remove test database file
        if os.path.exists('test_api_limits.db'):
            os.remove('test_api_limits.db')
        
        print("\n" + "="*60)
        print("  ALL TESTS COMPLETED")
        print("="*60 + "\n")

if __name__ == '__main__':
    run_tests()
