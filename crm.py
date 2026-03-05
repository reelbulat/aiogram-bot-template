import re
from typing import Iterable, Tuple, List, Dict, Any, Optional

from sqlalchemy import text
from db import engine


def _norm(s: str) -> str:
    s = s.strip().lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s)
    return s


def _parse_line_qty(line: str) -> Tuple[str, int]:
    """
    Принимает:
      "600x 2шт" -> ("600x", 2)
      "систенд 40 x4" -> ("систенд 40", 4)
      "F22x" -> ("F22x", 1)
    """
    raw = (line or "").strip()
    if not raw:
        return "", 0

    t = _norm(raw)
    qty = 1

    m = re.search(r"(\d+)\s*шт", t)
    if m:
        qty = int(m.group(1))
        name = raw[: m.start()].strip()
        return name or raw, max(qty, 1)

    m = re.search(r"(?:\s|^)(?:x|х)\s*(\d+)\s*$", t)
    if m:
        qty = int(m.group(1))
        name = raw[: raw.lower().rfind(m.group(0).strip())].strip()
        # на всякий случай, если вырезалось криво:
        name = name if name else raw
        return name, max(qty, 1)

    # вариант "4" в конце
    parts = raw.split()
    if len(parts) >= 2 and parts[-1].isdigit():
        qty = int(parts[-1])
        name = " ".join(parts[:-1]).strip()
        return name, max(qty, 1)

    return raw, 1


# ---------------- RENTERS ----------------

def get_or_create_renter(name: str) -> Dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValueError("empty renter name")

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, display_name FROM renters WHERE lower(display_name)=lower(:n) LIMIT 1"),
            {"n": name},
        ).fetchone()

        if row:
            return {"id": int(row[0]), "name": str(row[1])}

        row2 = conn.execute(
            text("INSERT INTO renters (full_name, display_name) VALUES (:fn, :dn) RETURNING id"),
            {"fn": name, "dn": name},
        ).fetchone()

        return {"id": int(row2[0]), "name": name}


# ---------------- QUOTES ----------------

def _next_quote_number(conn) -> str:
    row = conn.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM quotes")).fetchone()
    n = int(row[0]) if row and row[0] is not None else 1
    return str(n).zfill(5)


def create_quote(
    title: str,
    renter_id: int,
    renter_name: str,
    load_date: str,     # YYYY-MM-DD
    load_time: str,     # HH:MM
    shifts: int,
    return_time: Optional[str],
    status: str = "draft",
) -> Dict[str, Any]:
    title = (title or "").strip() or renter_name
    shifts = int(shifts)

    with engine.begin() as conn:
        quote_number = _next_quote_number(conn)

        row = conn.execute(
            text("""
                INSERT INTO quotes
                (quote_number, project_name, renter_id, load_date, load_time, shifts, return_time,
                 client_total, subrental_total, profit_total, status)
                VALUES
                (:qn, :pn, :rid, :ld::date, :lt::time, :sh, :rt::time,
                 0, 0, 0, :st)
                RETURNING id
            """),
            {
                "qn": quote_number,
                "pn": title,
                "rid": int(renter_id),
                "ld": load_date,
                "lt": load_time,
                "sh": shifts,
                "rt": return_time,
                "st": status,
            },
        ).fetchone()

        qid = int(row[0])

    return {
        "id": qid,
        "number": quote_number,
        "title": title,
        "renter_name": renter_name,
        "load_date": load_date,
        "load_time": load_time,
        "shifts": shifts,
        "return_time": return_time,
        "status": status,
        "items_text": "— пока пусто —",
        "client_sum": 0,
        "subrent_sum": 0,
        "profit": 0,
    }


def get_last_quote() -> Optional[Dict[str, Any]]:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT q.id, q.quote_number, q.project_name, r.display_name,
                   q.load_date, q.load_time, q.shifts, q.return_time,
                   q.client_total, q.subrental_total, q.profit_total, q.status
            FROM quotes q
            JOIN renters r ON r.id = q.renter_id
            ORDER BY q.id DESC
            LIMIT 1
        """)).fetchone()

        if not row:
            return None

        quote_id = int(row[0])

        items_rows = conn.execute(text("""
            SELECT title, qty, unit_price_client
            FROM quote_items
            WHERE quote_id = :qid
            ORDER BY id ASC
        """), {"qid": quote_id}).fetchall()

        if not items_rows:
            items_text = "— пока пусто —"
        else:
            lines = []
            for t, qty, up in items_rows:
                qty = int(qty)
                up = int(up)
                if qty == 1:
                    lines.append(f"• {t} — {up} ₽")
                else:
                    lines.append(f"• {t} ×{qty} — {up} ₽")
            items_text = "\n".join(lines)

    return {
        "id": quote_id,
        "number": row[1],
        "title": row[2],
        "renter_name": row[3],
        "load_date": str(row[4]),
        "load_time": str(row[5])[:5],
        "shifts": int(row[6]),
        "return_time": (str(row[7])[:5] if row[7] is not None else None),
        "client_sum": int(row[8] or 0),
        "subrent_sum": int(row[9] or 0),
        "profit": int(row[10] or 0),
        "status": row[11] or "draft",
        "items_text": items_text,
    }


# ---------------- EQUIPMENT SEARCH ----------------

def find_equipment_by_alias(token: str) -> Optional[Dict[str, Any]]:
    t = _norm(token)
    if not t:
        return None

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, name, daily_price, status
                FROM equipment
                WHERE lower(name) LIKE :p
                   OR lower(aliases) LIKE :p
                LIMIT 1
            """),
            {"p": f"%{t}%"},
        ).fetchone()

    if not row:
        return None

    return {
        "id": int(row[0]),
        "name": str(row[1]),
        "daily_price": int(row[2] or 0),
        "status": str(row[3] or "ok"),
    }


# ---------------- ITEMS RESOLVE ----------------

def resolve_items(lines: Iterable[str], shifts: int = 1) -> Tuple[List[Dict[str, Any]], List[str], int]:
    """
    Находит позиции по алиасам/названию в таблице equipment.
    Возвращает items для записи в quote_items (цена уже умножена на shifts),
    not_found и items_sum (сумма клиента по умолчанию).
    """
    shifts = max(int(shifts), 1)

    items: List[Dict[str, Any]] = []
    not_found: List[str] = []
    items_sum = 0

    for raw in lines:
        name_part, qty = _parse_line_qty(raw)
        if not name_part or qty <= 0:
            continue

        eq = find_equipment_by_alias(name_part)
        if not eq:
            not_found.append(name_part)
            continue

        # цена за весь проект: daily_price * shifts
        unit_price_client = int(eq["daily_price"]) * shifts

        items.append({
            "equipment_id": int(eq["id"]),
            "title": str(eq["name"]),
            "qty": int(qty),
            "unit_price_client": unit_price_client,
        })

        items_sum += int(qty) * unit_price_client

    return items, not_found, items_sum


# ---------------- QUOTE ITEMS WRITE + TOTALS ----------------

def attach_items_to_quote(quote_id: int, items: List[Dict[str, Any]]) -> None:
    quote_id = int(quote_id)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM quote_items WHERE quote_id = :qid"), {"qid": quote_id})

        for it in items:
            conn.execute(
                text("""
                    INSERT INTO quote_items
                    (quote_id, equipment_id, title, qty, unit_price_client, is_subrental, unit_cost_subrental)
                    VALUES (:qid, :eid, :t, :q, :up, false, 0)
                """),
                {
                    "qid": quote_id,
                    "eid": int(it["equipment_id"]),
                    "t": str(it["title"]),
                    "q": int(it["qty"]),
                    "up": int(it["unit_price_client"]),
                },
            )

        # пересчитать totals по позициям
        row = conn.execute(
            text("""
                SELECT COALESCE(SUM(qty * unit_price_client), 0) AS client_total
                FROM quote_items
                WHERE quote_id = :qid
            """),
            {"qid": quote_id},
        ).fetchone()

        client_total = int(row[0] or 0)
        # субаренду не трогаем здесь
        sub_row = conn.execute(
            text("SELECT subrental_total FROM quotes WHERE id = :qid"),
            {"qid": quote_id},
        ).fetchone()
        sub_total = int(sub_row[0] or 0) if sub_row else 0
        profit_total = client_total - sub_total

        conn.execute(
            text("""
                UPDATE quotes
                SET client_total = :ct, profit_total = :pt
                WHERE id = :qid
            """),
            {"ct": client_total, "pt": profit_total, "qid": quote_id},
        )


def finalize_money(quote_id: int, client_sum: int, subrent_sum: int) -> None:
    quote_id = int(quote_id)
    client_sum = int(client_sum)
    subrent_sum = int(subrent_sum)
    profit = client_sum - subrent_sum

    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE quotes
                SET client_total = :ct,
                    subrental_total = :st,
                    profit_total = :pt
                WHERE id = :qid
            """),
            {"ct": client_sum, "st": subrent_sum, "pt": profit, "qid": quote_id},
        )
