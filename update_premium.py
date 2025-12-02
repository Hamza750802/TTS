import os
from sqlalchemy import create_engine, text

url = os.environ.get('DATABASE_URL')
if url and url.startswith('postgres://'):
    url = url.replace('postgres://', 'postgresql://', 1)

engine = create_engine(url)
with engine.connect() as conn:
    # First, list all users
    users = conn.execute(text('SELECT id, email, premium_tier FROM "user"'))
    print("Existing users:")
    for row in users:
        print(f"  {row}")
    
    # Update
    result = conn.execute(text("""
        UPDATE "user" 
        SET premium_tier = 'premium_pro', 
            premium_chars_used = 0, 
            premium_chars_reset_at = NOW() + INTERVAL '30 days' 
        WHERE LOWER(email) = LOWER('Hamzaarshad0515@gmail.com')
    """))
    conn.commit()
    print(f'\nUpdated {result.rowcount} row(s)')
