from datetime import date, time
from sqlalchemy import text
from db import engine


# ---------- QUOTES ----------

def _next_quote_number() -> str:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM quotes")).fetchone()
        n = int(row[0]) if row and row[0] is not None else 1
    return str(n).zfill(5)


def get_or_create_renter(display_name: str, full_name: str | None = None) -> int:
    display_name = display_name.strip()
    full_name = (full_name or display_name).strip()

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM renters WHERE display_name = :dn LIMIT 1"),
            {"dn": display_name},
        ).fetchone()
        if row:
            return int(row[0])

        row2 = conn.execute(
            text("INSERT INTO renters (full_name, display_name) VALUES (:fn, :dn) RETURNING id"),
            {"fn": full_name, "dn": display_name},
        ).fetchone()
        return int(row2[0])


def create_quote(
    project_name: str | None,
    renter_display_name: str,
    renter_full_name: str | None,
    load_date: date,
    load_time: time,
    shifts: int,
    return_time: time | None,
    client_total: int,
    subrental_total: int,
) -> dict:
    quote_number = _next_quote_number()
    renter_id = get_or_create_renter(renter_display_name, renter_full_name)

    project_name = (project_name or "").strip() or None
    profit_total = max(0, int(client_total) - int(subrental_total))

    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO quotes
                (quote_number, project_name, renter_id, load_date, load_time, shifts, return_time,
                 client_total, subrental_total, profit_total)
                VALUES
                (:qn, :pn, :rid, :ld, :lt, :sh, :rt,
                 :ct, :st, :pt)
                RETURNING id
                """
            ),
            {
                "qn": quote_number,
                "pn": project_name,
                "rid": renter_id,
                "ld": load_date,
                "lt": load_time,
                "sh": shifts,
                "rt": return_time,
                "ct": int(client_total),
                "st": int(subrental_total),
                "pt": int(profit_total),
            },
        ).fetchone()

        quote_id = int(row[0])

        renter = conn.execute(
            text("SELECT full_name, display_name FROM renters WHERE id = :id"),
            {"id": renter_id},
        ).fetchone()

    return {
        "id": quote_id,
        "quote_number": quote_number,
        "project_name": project_name,
        "renter_full_name": renter[0] if renter else renter_full_name,
        "renter_display_name": renter[1] if renter else renter_display_name,
        "load_date": load_date,
        "load_time": load_time,
        "shifts": shifts,
        "return_time": return_time,
        "client_total": int(client_total),
        "subrental_total": int(subrental_total),
        "profit_total": int(profit_total),
    }


def get_last_quote():
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT q.id, q.quote_number, q.project_name, r.display_name,
                       q.load_date, q.load_time, q.shifts, q.return_time,
                       q.client_total, q.subrental_total, q.profit_total, q.status
                FROM quotes q
                JOIN renters r ON r.id = q.renter_id
                ORDER BY q.id DESC
                LIMIT 1
                """
            )
        ).fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "quote_number": row[1],
        "project_name": row[2],
        "renter_display_name": row[3],
        "load_date": row[4],
        "load_time": row[5],
        "shifts": row[6],
        "return_time": row[7],
        "client_total": row[8],
        "subrental_total": row[9],
        "profit_total": row[10],
        "status": row[11],
    }


# ---------- EQUIPMENT CATALOG ----------

def add_equipment(name: str, category: str, daily_price: int, purchase_price: int | None, qty_total: int, status: str, aliases: str) -> int:
    name = name.strip()
    aliases = (aliases or "").strip()

    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO equipment (name, category, daily_price, purchase_price, qty_total, status, aliases)
                VALUES (:n, :c, :dp, :pp, :qty, :st, :al)
                RETURNING id
                """
            ),
            {
                "n": name,
                "c": category,
                "dp": int(daily_price),
                "pp": int(purchase_price) if purchase_price is not None else None,
                "qty": int(qty_total),
                "st": status,
                "al": aliases,
            },
        ).fetchone()
        return int(row[0])


def find_equipment_by_alias(token: str):
    """
    Поиск по алиасам/названию.
    token: '600x' -> найдём equipment, где aliases содержит '600x' или name содержит.
    """
    t = token.strip().lower()
    if not t:
        return None

    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, name, category, daily_price, qty_total, status
                FROM equipment
                WHERE lower(name) LIKE :p
                   OR lower(aliases) LIKE :p2
                LIMIT 1
                """
            ),
            {"p": f"%{t}%", "p2": f"%{t}%"},
        ).fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "name": row[1],
        "category": row[2],
        "daily_price": row[3],
        "qty_total": row[4],
        "status": row[5],
    }


# ---------- QUOTE ITEMS ----------

def add_quote_item(quote_id: int, title: str, qty: int, unit_price_client: int, equipment_id: int | None = None, is_subrental: bool = False, unit_cost_subrental: int = 0):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO quote_items (quote_id, equipment_id, title, qty, unit_price_client, is_subrental, unit_cost_subrental)
                VALUES (:qid, :eid, :t, :q, :up, :sub, :cost)
                """
            ),
            {
                "qid": int(quote_id),
                "eid": int(equipment_id) if equipment_id is not None else None,
                "t": title,
                "q": int(qty),
                "up": int(unit_price_client),
                "sub": bool(is_subrental),
                "cost": int(unit_cost_subrental),
            },
        )


def recalc_quote_totals(quote_id: int):
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                  COALESCE(SUM(qty * unit_price_client), 0) AS client_total,
                  COALESCE(SUM(CASE WHEN is_subrental THEN qty * unit_cost_subrental ELSE 0 END), 0) AS sub_total
                FROM quote_items
                WHERE quote_id = :qid
                """
            ),
            {"qid": int(quote_id)},
        ).fetchone()

        client_total = int(row[0]) if row else 0
        sub_total = int(row[1]) if row else 0
        profit_total = max(0, client_total - sub_total)

        conn.execute(
            text(
                """
                UPDATE quotes
                SET client_total = :ct, subrental_total = :st, profit_total = :pt
                WHERE id = :qid
                """
            ),
            {"ct": client_total, "st": sub_total, "pt": profit_total, "qid": int(quote_id)},
        )

    return client_total, sub_total, profit_total


def get_quote_items(quote_id: int):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT title, qty, unit_price_client, is_subrental, unit_cost_subrental
                FROM quote_items
                WHERE quote_id = :qid
                ORDER BY id ASC
                """
            ),
            {"qid": int(quote_id)},
        ).fetchall()

    out = []
    for r in rows:
        out.append(
            {
                "title": r[0],
                "qty": r[1],
                "unit_price_client": r[2],
                "is_subrental": r[3],
                "unit_cost_subrental": r[4],
            }
        )
    return out
