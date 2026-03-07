from __future__ import annotations

import re
from typing import Iterable, Tuple, List, Dict, Any, Optional

from sqlalchemy import text
from db import engine


# ----------------- Renters -----------------

def get_or_create_renter(name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("renter name is empty")

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, display_name FROM renters WHERE display_name = :n LIMIT 1"),
            {"n": name},
        ).fetchone()

        if row:
            return {"id": int(row[0]), "name": row[1]}

        row2 = conn.execute(
            text("INSERT INTO renters (display_name, full_name) VALUES (:n, :n) RETURNING id"),
            {"n": name},
        ).fetchone()
        return {"id": int(row2[0]), "name": name}


# ----------------- Quotes -----------------

def _next_quote_number() -> str:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM quotes")).fetchone()
        n = int(row[0]) if row and row[0] is not None else 1
    return str(n).zfill(5)


def create_quote(
    title: str,
    renter_id: int,
    renter_name: str,
    load_date: str,       # "YYYY-MM-DD"
    load_time: str,       # "HH:MM"
    shifts: int,
    return_time: Optional[str],  # "HH:MM" or None
    status: str = "draft",
) -> dict:
    number = _next_quote_number()
    title = (title or "").strip()

    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO quotes
                (quote_number, project_name, renter_id, load_date, load_time, shifts, return_time,
                 client_total, subrental_total, profit_total, status)
                VALUES
                (:qn, :pn, :rid, :ld, :lt, :sh, :rt,
                 0, 0, 0, :st)
                RETURNING id
                """
            ),
            {
                "qn": number,
                "pn": title if title else None,
                "rid": int(renter_id),
                "ld": load_date,
                "lt": load_time,
                "sh": int(shifts),
                "rt": return_time,
                "st": status,
            },
        ).fetchone()
        quote_id = int(row[0])

    return {
        "id": quote_id,
        "number": number,
        "title": title,
        "renter_id": renter_id,
        "renter_name": renter_name,
        "load_date": load_date,
        "load_time": load_time,
        "shifts": shifts,
        "return_time": return_time,
        "client_sum": 0,
        "subrent_sum": 0,
        "profit": 0,
        "status": status,
        "items_text": "",
    }


def get_last_quote() -> Optional[dict]:
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

    quote_id = int(row[0])

    items_text = render_quote_items_text(quote_id)

    return {
        "id": quote_id,
        "number": row[1],
        "title": row[2] or "",
        "renter_name": row[3] or "",
        "load_date": str(row[4]),
        "load_time": str(row[5])[:5],
        "shifts": int(row[6]),
        "return_time": (str(row[7])[:5] if row[7] else None),
        "client_sum": int(row[8] or 0),
        "subrent_sum": int(row[9] or 0),
        "profit": int(row[10] or 0),
        "status": row[11] or "draft",
        "items_text": items_text,
    }


# ----------------- Quote items -----------------

def clear_quote_items(quote_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM quote_items WHERE quote_id = :qid"), {"qid": int(quote_id)})


def add_quote_item(
    quote_id: int,
    title: str,
    qty: int,
    unit_price_client: int,
    equipment_id: Optional[int] = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO quote_items (quote_id, equipment_id, title, qty, unit_price_client,
                                         is_subrental, unit_cost_subrental)
                VALUES (:qid, :eid, :t, :q, :up, false, 0)
                """
            ),
            {
                "qid": int(quote_id),
                "eid": int(equipment_id) if equipment_id is not None else None,
                "t": title,
                "q": int(qty),
                "up": int(unit_price_client),
            },
        )


def recalc_quote_totals(quote_id: int) -> tuple[int, int, int]:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT COALESCE(SUM(qty * unit_price_client), 0) AS client_total
                FROM quote_items
                WHERE quote_id = :qid
                """
            ),
            {"qid": int(quote_id)},
        ).fetchone()

        client_total = int(row[0] or 0)
        sub_total = int(
            conn.execute(
                text(
                    """
                    SELECT COALESCE(SUM(CASE WHEN is_subrental THEN qty * unit_cost_subrental ELSE 0 END), 0)
                    FROM quote_items
                    WHERE quote_id = :qid
                    """
                ),
                {"qid": int(quote_id)},
            ).fetchone()[0]
        )

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


def finalize_money(quote_id: int, client_sum: int, subrent_sum: int) -> None:
    profit = max(0, int(client_sum) - int(subrent_sum))
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE quotes
                SET client_total = :ct, subrental_total = :st, profit_total = :pt
                WHERE id = :qid
                """
            ),
            {"ct": int(client_sum), "st": int(subrent_sum), "pt": profit, "qid": int(quote_id)},
        )


def render_quote_items_text(quote_id: int) -> str:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT title, qty
                FROM quote_items
                WHERE quote_id = :qid
                ORDER BY id ASC
                """
            ),
            {"qid": int(quote_id)},
        ).fetchall()

    if not rows:
        return "— пока пусто —"

    out = []
    for title, qty in rows:
        q = int(qty or 1)
        if q == 1:
            out.append(f"• {title}")
        else:
            out.append(f"• {title} ×{q}")
    return "\n".join(out)


# ----------------- Equipment lookup + resolve -----------------

def find_equipment_by_alias(token: str) -> Optional[dict]:
    t = (token or "").strip().lower()
    if not t:
        return None

    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, name, daily_price, aliases
                FROM equipment
                WHERE lower(name) LIKE :p
                   OR lower(aliases) LIKE :p
                LIMIT 1
                """
            ),
            {"p": f"%{t}%"},
        ).fetchone()

    if not row:
        return None

    return {
        "id": int(row[0]),
        "name": row[1],
        "daily_price": int(row[2] or 0),
        "aliases": row[3] or "",
    }


_QTY_PATTERNS = [
    re.compile(r"(?:(\d+)\s*шт)\b", re.I),
    re.compile(r"\b(?:x|х)\s*(\d+)\b", re.I),
    re.compile(r"\b(\d+)\s*(?:pcs|pc)\b", re.I),
]


def _extract_qty(s: str) -> tuple[str, int]:
    txt = s.strip()
    qty = 1
    for rx in _QTY_PATTERNS:
        m = rx.search(txt)
        if m:
            qty = max(1, int(m.group(1)))
            txt = (txt[:m.start()] + " " + txt[m.end():]).strip()
            break
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt, qty


def resolve_items(lines: Iterable[str], shifts: int = 1) -> Tuple[List[Dict[str, Any]], List[str], int]:
    """
    Возвращает:
      items: [{equipment_id, title, qty, unit_price_client}]
      not_found: [raw ...]
      items_sum: сумма по каталожным daily_price * qty * shifts
    """
    items: List[Dict[str, Any]] = []
    not_found: List[str] = []
    items_sum = 0

    shifts = max(int(shifts), 1)

    for raw in lines:
        raw = (raw or "").strip()
        if not raw:
            continue

        cleaned, qty = _extract_qty(raw)
        token = cleaned.lower()

        eq = find_equipment_by_alias(token)
        if not eq:
            not_found.append(raw)
            continue

        unit_price = int(eq["daily_price"] or 0) * shifts
        items_sum += unit_price * qty

        items.append(
            {
                "equipment_id": eq["id"],
                "title": eq["name"],
                "qty": qty,
                "unit_price_client": unit_price,
            }
        )

    return items, not_found, items_sum

def attach_items_to_quote(quote_id: int, items: List[Dict[str, Any]]) -> None:
    clear_quote_items(quote_id)
    for it in items:
        add_quote_item(
            quote_id=quote_id,
            title=it["title"],
            qty=int(it["qty"]),
            unit_price_client=int(it["unit_price_client"]),
            equipment_id=int(it["equipment_id"]),
        )
    recalc_quote_totals(quote_id)
