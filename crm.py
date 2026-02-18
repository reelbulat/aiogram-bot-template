from datetime import datetime, date, time
from sqlalchemy import text
from db import engine


def _next_quote_number() -> str:
    """Возвращает следующий 5-значный номер сметы: 00001, 00002..."""
    with engine.connect() as conn:
        row = conn.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM quotes")).fetchone()
        n = int(row[0]) if row and row[0] is not None else 1
    return str(n).zfill(5)


def get_or_create_renter(display_name: str, full_name: str | None = None) -> int:
    """Создать арендатора, если его нет. Возвращает renter_id."""
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
            text(
                "INSERT INTO renters (full_name, display_name) VALUES (:fn, :dn) RETURNING id"
            ),
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
    """
    Создаёт смету (черновик).
    profit_total пока считаем как client_total - subrental_total.
    """
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
                 client_total, subrental_total, profit_total,
                 discount_camera, discount_light, status, client_payment_status, subrental_payment_status)
                VALUES
                (:qn, :pn, :rid, :ld, :lt, :sh, :rt,
                 :ct, :st, :pt,
                 0, 0, 'draft', 'не оплачено', 'не оплачено')
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

        # Подтягиваем отображаемое имя арендатора
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


def get_last_quote() -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT q.quote_number, q.project_name, r.display_name, q.load_date, q.load_time,
                       q.shifts, q.return_time, q.client_total, q.subrental_total, q.profit_total, q.status
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
        "quote_number": row[0],
        "project_name": row[1],
        "renter_display_name": row[2],
        "load_date": row[3],
        "load_time": row[4],
        "shifts": row[5],
        "return_time": row[6],
        "client_total": row[7],
        "subrental_total": row[8],
        "profit_total": row[9],
        "status": row[10],
    }
