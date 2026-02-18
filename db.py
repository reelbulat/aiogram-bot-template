import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def init_db():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        conn.commit()
