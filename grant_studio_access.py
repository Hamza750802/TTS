#!/usr/bin/env python3
"""
Grant Studio Voices access to a user.
Run on Railway: railway run python grant_studio_access.py
"""
import os
from sqlalchemy import create_engine, text

url = os.environ.get('DATABASE_URL')
if not url:
    print("ERROR: DATABASE_URL not set")
    exit(1)

if url.startswith('postgres://'):
    url = url.replace('postgres://', 'postgresql://', 1)

EMAIL = 'hamzaarshad0515@gmail.com'

engine = create_engine(url)
with engine.connect() as conn:
    # First, check if vibevoice columns exist and add them if not
    print("Checking/adding vibevoice columns...")
    
    try:
        conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS has_vibevoice BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS vibevoice_tier VARCHAR(50)"))
        conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS vibevoice_char_limit INTEGER DEFAULT 600000"))
        conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS vibevoice_chars_used INTEGER DEFAULT 0"))
        conn.commit()
        print("✓ Columns ready")
    except Exception as e:
        print(f"Column setup: {e}")
    
    # Check if user exists
    result = conn.execute(text('SELECT id, email FROM "user" WHERE LOWER(email) = LOWER(:email)'), {'email': EMAIL})
    user = result.fetchone()
    
    if not user:
        print(f"User not found: {EMAIL}")
        exit(1)
    
    print(f"Found user: {user}")
    
    # Grant Studio Voices access
    conn.execute(text("""
        UPDATE "user" 
        SET has_vibevoice = TRUE,
            vibevoice_tier = 'studio',
            vibevoice_char_limit = 600000,
            vibevoice_chars_used = 0
        WHERE LOWER(email) = LOWER(:email)
    """), {'email': EMAIL})
    conn.commit()
    
    # Verify
    result = conn.execute(text('SELECT id, email, has_vibevoice, vibevoice_tier, vibevoice_char_limit, vibevoice_chars_used FROM "user" WHERE LOWER(email) = LOWER(:email)'), {'email': EMAIL})
    user = result.fetchone()
    print(f"\n✓ Studio Voices granted!")
    print(f"  Email: {user[1]}")
    print(f"  has_vibevoice: {user[2]}")
    print(f"  vibevoice_tier: {user[3]}")
    print(f"  Hours remaining: {(user[4] - user[5]) / 60000:.1f}")
