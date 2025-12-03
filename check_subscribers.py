"""Quick script to check subscribers in the database"""
import os
import sys
sys.path.insert(0, 'webapp')
from dotenv import load_dotenv
load_dotenv()

database_url = os.environ.get('DATABASE_URL')
if not database_url:
    print("No DATABASE_URL found in environment")
    sys.exit(1)

if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

from sqlalchemy import create_engine, text
engine = create_engine(database_url)

with engine.connect() as conn:
    # Get all users with their subscription info
    result = conn.execute(text("""
        SELECT 
            id,
            email,
            subscription_tier,
            stripe_subscription_id,
            chars_used,
            char_limit,
            premium_chars_used,
            premium_char_limit,
            created_at
        FROM "user"
        ORDER BY created_at DESC
        LIMIT 50
    """))
    
    rows = list(result)
    
    print("=" * 130)
    print(f"{'ID':<5} {'Email':<40} {'Tier':<12} {'Stripe Sub':<20} {'Chars':<10} {'Premium':<10} {'Created':<20}")
    print("=" * 130)
    
    for row in rows:
        tier = row[2] or 'free'
        stripe_sub = (row[3] or '-')[:18]
        chars = row[4] or 0
        prem_chars = row[6] or 0
        created = str(row[8])[:19] if row[8] else '-'
        email = row[1][:38] if row[1] else '-'
        print(f"{row[0]:<5} {email:<40} {tier:<12} {stripe_sub:<20} {chars:<10} {prem_chars:<10} {created:<20}")
    
    # Summary counts
    result = conn.execute(text("""
        SELECT 
            COALESCE(subscription_tier, 'free') as tier,
            COUNT(*) as count
        FROM "user"
        GROUP BY subscription_tier
        ORDER BY count DESC
    """))
    
    print()
    print("=" * 50)
    print("SUBSCRIPTION TIER SUMMARY:")
    print("=" * 50)
    for row in result:
        tier_name = row[0] if row[0] else 'free'
        print(f"  {tier_name}: {row[1]} users")
    
    # Total count
    result = conn.execute(text('SELECT COUNT(*) FROM "user"'))
    total = result.scalar()
    print(f"\n  TOTAL USERS: {total}")
