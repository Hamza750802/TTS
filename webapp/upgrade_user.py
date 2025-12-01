import sqlite3

conn = sqlite3.connect('C:/TTS-main/webapp/users.db')
c = conn.cursor()

# Update user to pro
c.execute("UPDATE user SET subscription_status='lifetime' WHERE email='hamzaarshad15121@gmail.com'")
conn.commit()

# Verify
c.execute("SELECT email, subscription_status, chars_used FROM user WHERE email='hamzaarshad15121@gmail.com'")
row = c.fetchone()
print(f"Email: {row[0]}")
print(f"subscription_status: {row[1]}")
print(f"chars_used: {row[2]}")
print("DONE! User now has PRO/Lifetime access.")
conn.close()
