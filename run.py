import asyncio
import os
import re
from datetime import datetime, date, time
from typing import Dict, Any, List, Tuple, Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from sqlalchemy import text

from db import engine, init_db

# ты уже создал catalog_seed.py
from catalog_seed import seed_catalog


# =========================
# ACCESS CONTROL
# =========================
ALLOWED_USERS = {
    586702928,  # Булат
    384857319,  # Рифкат
}

STATUS_EMOJI = {
    "draft": "🟡",
    "confirmed": "🟢",
    "done": "🔵",
    "cancelled": "🔴",
}

BOT_TOKEN = os.getenv("BOT_TOKEN")

# простое состояние формы (в памяти)
FORM: Dict[int, Dict[str, Any]] = {}

# =========================
# DB: собственные таблицы (crm_*)
# =========================
DDL = """
CREATE TABLE IF NOT EXISTS crm_equipment (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  category TEXT,
  day_price INTEGER NOT NULL DEFAULT 0,
  buy_price INTEGER,
  qty INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'ok',
  aliases TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS crm_renters (
  id SERIAL PRIMARY KEY,
  full_name TEXT NOT NULL UNIQUE,
  phone TEXT,
  telegram TEXT,
  socials TEXT,
  aliases TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS crm_quotes (
  id SERIAL PRIMARY KEY,
  number INTEGER NOT NULL UNIQUE,
  title TEXT NOT NULL,
  renter_id INTEGER NOT NULL REFERENCES crm_renters(id),
  load_date DATE NOT NULL,
  load_time TIME NOT NULL,
  shifts INTEGER NOT NULL,
  return_time TIME,
  status TEXT NOT NULL DEFAULT 'draft',
  client_sum INTEGER NOT NULL DEFAULT 0,
  subrent_sum INTEGER NOT NULL DEFAULT 0,
  profit INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS crm_quote_items (
  id SERIAL PRIMARY KEY,
  quote_id INTEGER NOT NULL REFERENCES crm_quotes(id) ON DELETE CASCADE,
  equipment_id INTEGER NOT NULL REFERENCES crm_equipment(id),
  qty INTEGER NOT NULL DEFAULT 1,
  day_price INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_crm_equipment_aliases ON crm_equipment USING gin (to_tsvector('simple', aliases));
CREATE INDEX IF NOT EXISTS idx_crm_renters_aliases ON crm_renters USING gin (to_tsvector('simple', aliases));
"""


def norm(s: str) -> str:
    s = s.strip().lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s)
    return s


def ensure_db():
    init_db()
    with engine.begin() as conn:
        conn.execute(text(DDL))


def is_allowed(message: types.Message) -> bool:
    return bool(message.from_user and message.from_user.id in ALLOWED_USERS)


def status_label(status: str) -> str:
    em = STATUS_EMOJI.get(status, "⚪️")
    return f"{em} {status}"


def parse_date(s: str) -> date:
    s = s.strip()
    # DD.MM.YYYY
    d, m, y = s.split(".")
    return date(int(y), int(m), int(d))


def parse_time(s: str) -> time:
    s = s.strip()
    hh, mm = s.split(":")
    return time(int(hh), int(mm))


def parse_qty(token: str) -> Optional[int]:
    t = norm(token)
    # варианты: 2, x2, *2, 2шт, 2 шт, х2
    m = re.search(r"(\d+)", t)
    if not m:
        return None
    return int(m.group(1))


def split_line_to_name_qty(line: str) -> Tuple[str, int]:
    """
    "600x 2шт" -> ("600x", 2)
    "систенд 40 x4" -> ("систенд 40", 4)
    "F22x" -> ("F22x", 1)
    """
    raw = line.strip()
    if not raw:
        return "", 0

    # если есть явное количество в конце
    parts = raw.split()
    if len(parts) >= 2:
        q = parse_qty(parts[-1])
        if q is not None:
            name = " ".join(parts[:-1]).strip()
            return name, max(q, 1)

    # если внутри "x4" или "×4" и т.п.
    m = re.search(r"(.*?)(?:\s*[xх×\*]\s*(\d+))\s*$", raw, flags=re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        q = int(m.group(2))
        return name, max(q, 1)

    return raw.strip(), 1


def find_equipment_by_alias(conn, query: str) -> Optional[Dict[str, Any]]:
    q = norm(query)
    # ищем по name или aliases (aliases = строка с запятыми)
    row = conn.execute(
        text("""
            SELECT id, name, day_price
            FROM crm_equipment
            WHERE lower(name) = :q
               OR lower(aliases) LIKE :likeq
               OR lower(name) LIKE :likeq2
            LIMIT 1
        """),
        {"q": q, "likeq": f"%{q}%", "likeq2": f"%{q}%"},
    ).fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "day_price": row[2]}


def get_or_create_renter(conn, name_or_alias: str) -> int:
    q = norm(name_or_alias)
    row = conn.execute(
        text("""
            SELECT id FROM crm_renters
            WHERE lower(full_name) = :q OR lower(aliases) LIKE :likeq
            LIMIT 1
        """),
        {"q": q, "likeq": f"%{q}%"},
    ).fetchone()
    if row:
        return int(row[0])

    # если новый — создаём минимально (контакты добьём потом отдельной командой, сейчас MVP)
    full_name = name_or_alias.strip()
    aliases = q
    new_id = conn.execute(
        text("INSERT INTO crm_renters(full_name, aliases) VALUES (:n, :a) RETURNING id"),
        {"n": full_name, "a": aliases},
    ).fetchone()[0]
    return int(new_id)


def next_quote_number(conn) -> int:
    row = conn.execute(text("SELECT COALESCE(MAX(number), 0) FROM crm_quotes")).fetchone()
    return int(row[0]) + 1


def quote_title_or_renter(title: str, renter_name: str) -> str:
    t = title.strip()
    if t == "-" or t == "":
        return renter_name.strip()
    return t


def format_quote(conn, quote_id: int) -> str:
    q = conn.execute(text("""
        SELECT q.number, q.title, r.full_name, q.load_date, q.load_time, q.shifts, q.return_time,
               q.client_sum, q.subrent_sum, q.profit, q.status
        FROM crm_quotes q
        JOIN crm_renters r ON r.id = q.renter_id
        WHERE q.id = :id
    """), {"id": quote_id}).fetchone()

    if not q:
        return "Смета не найдена."

    number, title, renter_full, load_date, load_time, shifts, return_time, client_sum, subrent_sum, profit, status = q

    items = conn.execute(text("""
        SELECT e.name, qi.qty, qi.day_price
        FROM crm_quote_items qi
        JOIN crm_equipment e ON e.id = qi.equipment_id
        WHERE qi.quote_id = :id
        ORDER BY e.name
    """), {"id": quote_id}).fetchall()

    lines = []
    lines.append("Смета создана ✅")
    lines.append("")
    lines.append(f"{title} — #{int(number):05d}")
    lines.append(f"Дата: {load_date.strftime('%d.%m.%Y')}")
    lines.append(f"Время: {load_time.strftime('%H:%M')}")
    lines.append(f"Смен: {int(shifts)}")
    if return_time is not None:
        lines.append(f"Возврат: {return_time.strftime('%H:%M')}")
    lines.append("")
    lines.append("Позиции техники:")
    if not items:
        lines.append("— пока пусто —")
    else:
        for name, qty, day_price in items:
            if int(qty) == 1:
                lines.append(f"• {name} — {int(day_price)} ₽/смена")
            else:
                lines.append(f"• {name} ×{int(qty)} — {int(day_price)} ₽/смена")
    lines.append("")
    lines.append(f"Сумма клиента: {int(client_sum)} ₽")
    lines.append(f"Субаренда: {int(subrent_sum)} ₽")
    lines.append(f"Прибыль: {int(profit)} ₽")
    lines.append(f"Статус: {status_label(str(status))}")
    lines.append("")
    lines.append("Команды:")
    lines.append("/new — новая смета")
    lines.append("/items — добавить/обновить технику")
    lines.append("/sub — субаренда (сумма)")
    lines.append("/last — последняя смета")
    lines.append("/seed_catalog — залить каталог")
    lines.append("/cancel — отменить ввод")
    return "\n".join(lines)


def recalc_sums(conn, quote_id: int):
    q = conn.execute(text("SELECT shifts, subrent_sum FROM crm_quotes WHERE id=:id"), {"id": quote_id}).fetchone()
    if not q:
        return
    shifts, subrent_sum = int(q[0]), int(q[1])

    items = conn.execute(text("""
        SELECT qty, day_price
        FROM crm_quote_items
        WHERE quote_id = :id
    """), {"id": quote_id}).fetchall()

    total = 0
    for qty, day_price in items:
        total += int(qty) * int(day_price) * shifts

    client_sum = total
    profit = client_sum - subrent_sum

    conn.execute(text("""
        UPDATE crm_quotes
        SET client_sum=:cs, profit=:p
        WHERE id=:id
    """), {"cs": client_sum, "p": profit, "id": quote_id})


# =========================
# BOT
# =========================
async def main():
    ensure_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # 1) ответ "нет доступа" для любых чужих
    @dp.message()
    async def deny_others(message: types.Message):
        if is_allowed(message):
            return  # дальше обработают другие хендлеры
        await message.answer("Нет доступа.")

    # 2) все реальные обработчики — только для ALLOWED
    # (фильтр на все сообщения ниже)
    dp.message.filter(F.from_user.func(lambda u: u is not None and u.id in ALLOWED_USERS))

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        await message.answer(
            "CRM бот работает ✅\n\n"
            "Команды:\n"
            "/new — новая смета\n"
            "/items — добавить/обновить технику\n"
            "/sub — указать субаренду\n"
            "/last — последняя смета\n"
            "/db — проверка базы\n"
            "/seed_catalog — залить каталог\n"
            "/cancel — отменить ввод\n"
        )

    @dp.message(Command("db"))
    async def cmd_db(message: types.Message):
        try:
            with engine.begin() as conn:
                conn.execute(text("SELECT 1"))
            await message.answer("База подключена ✅")
        except Exception as e:
            await message.answer(f"База НЕ подключена ❌\n{e}")

    @dp.message(Command("seed_catalog"))
    async def cmd_seed(message: types.Message):
        try:
            res = seed_catalog()
            # seed_catalog сам работает через твою engine/db
            # если там он пользуется другими таблицами — скажешь, адаптируем
            await message.answer(
                f"Каталог залит ✅\n"
                f"Добавлено: {res.get('added', 0)}\n"
                f"Пропущено: {res.get('skipped', 0)}"
            )
        except Exception as e:
            await message.answer(f"Ошибка сидирования каталога ❌\n{e}")

    @dp.message(Command("cancel"))
    async def cmd_cancel(message: types.Message):
        FORM.pop(message.from_user.id, None)
        await message.answer("Ок, отменил ввод.")

    @dp.message(Command("new"))
    async def cmd_new(message: types.Message):
        FORM[message.from_user.id] = {"step": "title"}
        await message.answer("Название проекта или '-' (если не указываем)")

    @dp.message(Command("last"))
    async def cmd_last(message: types.Message):
        with engine.begin() as conn:
            row = conn.execute(text("SELECT id FROM crm_quotes ORDER BY id DESC LIMIT 1")).fetchone()
            if not row:
                await message.answer("Смет пока нет.")
                return
            await message.answer(format_quote(conn, int(row[0])))

    @dp.message(Command("items"))
    async def cmd_items(message: types.Message):
        st = FORM.get(message.from_user.id)
        if not st or not st.get("quote_id"):
            await message.answer("Сначала создай смету: /new")
            return

        await message.answer(
            "Пришли список техники (каждая строка — позиция):\n"
            "пример:\n"
            "600x 2шт\n"
            "F22x\n"
            "систенд 40 x4\n\n"
            "Я сам посчитаю сумму по каталогу."
        )
        st["step"] = "items"

    @dp.message(Command("sub"))
    async def cmd_sub(message: types.Message):
        st = FORM.get(message.from_user.id)
        if not st or not st.get("quote_id"):
            await message.answer("Сначала создай смету: /new")
            return
        st["step"] = "subrent"
        await message.answer("Субаренда (сколько ты платишь другим). Число ₽ или 0")

    @dp.message()
    async def flow(message: types.Message):
        uid = message.from_user.id
        st = FORM.get(uid)
        if not st:
            return  # ничего не делаем, чтоб не мешать командам

        txt = (message.text or "").strip()

        # ШАГ 1: title
        if st["step"] == "title":
            st["title_raw"] = txt
            st["step"] = "renter"
            await message.answer("Арендатор (имя/фамилия)")
            return

        # ШАГ 2: renter
        if st["step"] == "renter":
            st["renter_name"] = txt
            st["step"] = "date"
            await message.answer("Дата ДД.ММ.ГГГГ")
            return

        # ШАГ 3: date
        if st["step"] == "date":
            try:
                st["load_date"] = parse_date(txt)
            except Exception:
                await message.answer("Не понял дату. Формат: ДД.ММ.ГГГГ")
                return
            st["step"] = "time"
            await message.answer("Время погрузки ЧЧ:ММ")
            return

        # ШАГ 4: time
        if st["step"] == "time":
            try:
                st["load_time"] = parse_time(txt)
            except Exception:
                await message.answer("Не понял время. Формат: ЧЧ:ММ")
                return
            st["step"] = "shifts"
            await message.answer("Количество смен (целое число), например 2")
            return

        # ШАГ 5: shifts
        if st["step"] == "shifts":
            try:
                shifts = int(txt)
                if shifts <= 0:
                    raise ValueError()
                st["shifts"] = shifts
            except Exception:
                await message.answer("Нужно целое число > 0.")
                return
            st["step"] = "return"
            await message.answer("Время возврата (ЧЧ:ММ) или '-' если неизвестно/пропуск")
            return

        # ШАГ 6: return time
        if st["step"] == "return":
            if txt == "-" or txt == "":
                st["return_time"] = None
            else:
                try:
                    st["return_time"] = parse_time(txt)
                except Exception:
                    await message.answer("Не понял. Введи ЧЧ:ММ или '-'")
                    return

            # создаём quote в базе
            with engine.begin() as conn:
                renter_id = get_or_create_renter(conn, st["renter_name"])
                number = next_quote_number(conn)
                title = quote_title_or_renter(st["title_raw"], st["renter_name"])

                row = conn.execute(
                    text("""
                        INSERT INTO crm_quotes(number, title, renter_id, load_date, load_time, shifts, return_time, status)
                        VALUES (:n, :t, :r, :d, :tm, :s, :rt, 'draft')
                        RETURNING id
                    """),
                    {
                        "n": number,
                        "t": title,
                        "r": renter_id,
                        "d": st["load_date"],
                        "tm": st["load_time"],
                        "s": st["shifts"],
                        "rt": st["return_time"],
                    },
                ).fetchone()

                st["quote_id"] = int(row[0])

                await message.answer(format_quote(conn, st["quote_id"]))
                await message.answer("Теперь добавь технику: /items")
                st["step"] = "idle"
            return

        # ШАГ: items (ввод списком)
        if st["step"] == "items":
            quote_id = st.get("quote_id")
            if not quote_id:
                await message.answer("Сначала /new")
                return

            lines = [l.strip() for l in txt.splitlines() if l.strip()]
            if not lines:
                await message.answer("Пусто. Пришли строки с техникой.")
                return

            not_found: List[str] = []
            found_items: List[Tuple[int, int, int]] = []  # (equipment_id, qty, day_price)

            with engine.begin() as conn:
                # очищаем прошлые позиции (чтобы "обновить комплект" легко)
                conn.execute(text("DELETE FROM crm_quote_items WHERE quote_id=:id"), {"id": quote_id})

                for line in lines:
                    name_part, qty = split_line_to_name_qty(line)
                    if not name_part:
                        continue

                    eq = find_equipment_by_alias(conn, name_part)
                    if not eq:
                        not_found.append(name_part)
                        continue

                    found_items.append((int(eq["id"]), int(qty), int(eq["day_price"])))

                if not found_items:
                    msg = "Ничего не добавил — все позиции не найдены.\n\n"
                    if not_found:
                        msg += "⚠️ Не нашёл в каталоге:\n" + "\n".join([f"- {x}" for x in not_found]) + "\n\n"
                    msg += "Добавь через /equip_new (позже) или сначала залей каталог: /seed_catalog"
                    await message.answer(msg)
                    return

                for equipment_id, qty, day_price in found_items:
                    conn.execute(
                        text("""
                            INSERT INTO crm_quote_items(quote_id, equipment_id, qty, day_price)
                            VALUES (:q, :e, :qty, :p)
                        """),
                        {"q": quote_id, "e": equipment_id, "qty": qty, "p": day_price},
                    )

                recalc_sums(conn, quote_id)
                out = format_quote(conn, quote_id)

                if not_found:
                    out += "\n\n⚠️ Не нашёл в каталоге:\n" + "\n".join([f"- {x}" for x in not_found])

                await message.answer(out)
                await message.answer("Если есть субаренда — введи: /sub")
                st["step"] = "idle"
            return

        # ШАГ: subrent
        if st["step"] == "subrent":
            quote_id = st.get("quote_id")
            if not quote_id:
                await message.answer("Сначала /new")
                return
            try:
                val = int(re.sub(r"[^\d]", "", txt)) if txt else 0
            except Exception:
                await message.answer("Нужно число ₽ (например 15000) или 0")
                return

            with engine.begin() as conn:
                conn.execute(text("UPDATE crm_quotes SET subrent_sum=:v WHERE id=:id"), {"v": val, "id": quote_id})
                recalc_sums(conn, quote_id)
                await message.answer(format_quote(conn, quote_id))
            st["step"] = "idle"
            return

        # idle — не мешаем
        return

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
