import logging
from sqlalchemy import create_engine, text

# URL from user's screenshot
url = "postgresql+pg8000://postgres:ReL5%2BAtsXh%2C8QeT@db.sjchqdukavrxdyufxcpg.supabase.co:5432/postgres"

print(f"Connecting to: {url}")
try:
    engine = create_engine(url)
    with engine.connect() as conn:
        res = conn.execute(text("SELECT 1"))
        print("Success! SELECT 1 returned:", res.scalar())
except Exception as e:
    print("FAILED TO CONNECT:")
    print(e)
