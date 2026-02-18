from sqlalchemy import text
from db import engine


def create_tables():
    with engine.begin() as conn:
        # renters
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS renters (
                    id SERIAL PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    display_name TEXT NOT NULL UNIQUE,
                    phone TEXT,
                    telegram TEXT,
                    socials TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                """
            )
        )

        # quotes
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS quotes (
                    id SERIAL PRIMARY KEY,
                    quote_number CHAR(5) NOT NULL UNIQUE,
                    project_name TEXT,
                    renter_id INT NOT NULL REFERENCES renters(id),

                    load_date DATE NOT NULL,
                    load_time TIME NOT NULL,
                    shifts INT NOT NULL,
                    return_time TIME,

                    client_total INT NOT NULL DEFAULT 0,
                    subrental_total INT NOT NULL DEFAULT 0,
                    profit_total INT NOT NULL DEFAULT 0,

                    status TEXT NOT NULL DEFAULT 'draft',
                    client_payment_status TEXT NOT NULL DEFAULT 'не оплачено',
                    subrental_payment_status TEXT NOT NULL DEFAULT 'не оплачено',

                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                """
            )
        )

        # equipment (каталог техники)
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS equipment (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL, -- camera / lens / media / light_head / grip / other
                    daily_price INT NOT NULL,
                    purchase_price INT,

                    qty_total INT NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'ок', -- 'ок' / 'ремонт'

                    aliases TEXT NOT NULL DEFAULT '', -- "600x,600 икс,апутур 600x"
                    times_rented INT NOT NULL DEFAULT 0,
                    revenue_total INT NOT NULL DEFAULT 0,

                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                """
            )
        )

        # quote_items (строки сметы)
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS quote_items (
                    id SERIAL PRIMARY KEY,
                    quote_id INT NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,

                    equipment_id INT REFERENCES equipment(id),
                    title TEXT NOT NULL,           -- название позиции (на случай субаренды/ручной)
                    qty INT NOT NULL DEFAULT 1,

                    unit_price_client INT NOT NULL DEFAULT 0, -- цена клиенту за единицу
                    is_subrental BOOLEAN NOT NULL DEFAULT FALSE,
                    unit_cost_subrental INT NOT NULL DEFAULT 0, -- себестоимость субаренды за единицу

                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                """
            )
        )
