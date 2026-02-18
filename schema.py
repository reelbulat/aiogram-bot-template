from sqlalchemy import text
from db import engine

DDL = [
    """
    CREATE TABLE IF NOT EXISTS renters (
        id SERIAL PRIMARY KEY,
        full_name TEXT NOT NULL,
        display_name TEXT NOT NULL,
        phone TEXT,
        telegram TEXT,
        social_link TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS quotes (
        id SERIAL PRIMARY KEY,
        quote_number CHAR(5) NOT NULL UNIQUE,
        project_name TEXT,
        renter_id INT NOT NULL REFERENCES renters(id),
        load_date DATE NOT NULL,
        load_time TIME NOT NULL,
        shifts INT NOT NULL CHECK (shifts > 0),
        return_time TIME,
        client_total INT NOT NULL CHECK (client_total >= 0),
        subrental_total INT NOT NULL DEFAULT 0 CHECK (subrental_total >= 0),
        profit_total INT NOT NULL CHECK (profit_total >= 0),
        discount_camera NUMERIC(5,2) NOT NULL DEFAULT 0,
        discount_light NUMERIC(5,2) NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'draft',
        client_payment_status TEXT NOT NULL DEFAULT 'не оплачено',
        subrental_payment_status TEXT NOT NULL DEFAULT 'не оплачено',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
]

def create_tables():
    with engine.begin() as conn:
        for q in DDL:
            conn.execute(text(q))
