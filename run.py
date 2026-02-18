import asyncio
import os
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from sqlalchemy import text

from db import engine, init_db
from schema import create_tables

from crm import (
    create_quote,
    get_last_quote,
    get_or_create_renter,
    add_equipment,
    find_equipment_by_alias,
    add_quote_item,
    recalc_quote_totals,
    get_quote_items,
)

ALLOWED_USERS = {
    586702928,
    384857319,
}

BOT_TOKEN = os.getenv("BOT_TOKEN")

FORM_QUOTE = {}
FORM_ITEMS = {}
FORM_EQUIP = {}


def allowed(message: types.Message):
    return message.from_user and message.from_user.id in ALLOWED_USERS


def parse_date(s: str):
    return datetime.strptime(s.strip(), "%d.%m.%Y").date()


def parse_time(s: str):
    return datetime.strptime(s.strip(), "%H:%M").time()


def fmt_quote(q, items=None):
    title = q.get("project_name") or q.get("renter_display_name") or "—"

    status_map = {
        "draft": "🟡 draft",
        "confirmed": "🟢 confirmed",
        "done": "🔵 done",
        "cancelled": "🔴 cancelled",
    }
    status = status_map.get(q.get("status"), "🟡 draft")

    lines = [
        f"{title} — #{q['quote_number']}",
        f"Дата: {q['load_date'].strftime('%d.%m.%Y')}",
        f"Время: {q['load_time'].strftime('%H:%M')}",
        f"Смен: {q['shifts']}",
    ]

    if q.get("return_time"):
        lines.append(f"Возврат: {q['return_time'].strftime('%H:%M')}")

    if items is not None:
        lines.append("")
        lines.append("Позиции техники:")
        if not items:
            lines.append("— пока пусто —")
        else:
            for it in items:
                lines.append(f"- {it['title']} — {it['qty']} шт — {it['unit_price_client']} ₽")

    lines += [
        "",
        f"Сумма клиента: {q['client_total']} ₽",
        f"Субаренда: {q['subrental_total']} ₽",
        f"Прибыль: {q['profit_total']} ₽",
        f"Статус: {status}",
    ]

    return "\n".join(lines)


def parse_items_lines(text_block):
    out = []
    for raw in text_block.splitlines():
        s0 = raw.strip()
        if not s0:
            continue

        s = s0.lower().replace("х", "x").replace("×", "x")
        qty = 1
        token = s

        m = re.search(r"x\s*(\d+)$", s)
        if m:
            qty = int(m.group(1))
            token = s[: m.start()].strip()
        else:
            m2 = re.search(r"(\d+)\s*(шт|x)?$", s)
            if m2:
                qty = int(m2.group(1))
                token = s[: m2.start()].strip()

        out.append((token, qty))
    return out


async def main():
    init_db()
    create_tables()

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        if not allowed(message):
            return
        await message.answer("CRM бот работает ✅")

    @dp.message(Command("db"))
    async def cmd_db(message: types.Message):
        if not allowed(message):
            return
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        await message.answer("База подключена ✅")

    @dp.message(Command("last"))
    async def cmd_last(message: types.Message):
        if not allowed(message):
            return
        q = get_last_quote()
        if not q:
            await message.answer("Смет нет")
            return
        items = get_quote_items(q["id"])
        await message.answer(fmt_quote(q, items))

    @dp.message(Command("new"))
    async def cmd_new(message: types.Message):
        if not allowed(message):
            return
        uid = message.from_user.id
        FORM_QUOTE[uid] = {"step": "project"}
        await message.answer("Название проекта или '-'")

    @dp.message(Command("items"))
    async def cmd_items(message: types.Message):
        if not allowed(message):
            return
        q = get_last_quote()
        if not q:
            await message.answer("Нет сметы")
            return
        FORM_ITEMS[message.from_user.id] = q["id"]
        await message.answer("Пришли список техники")

    @dp.message()
    async def text_handler(message: types.Message):
        if not allowed(message):
            return

        uid = message.from_user.id
        txt = message.text.strip()

        if uid in FORM_ITEMS:
            qid = FORM_ITEMS.pop(uid)
            pairs = parse_items_lines(txt)

            for token, qty in pairs:
                eq = find_equipment_by_alias(token)
                if not eq:
                    continue
                add_quote_item(
                    quote_id=qid,
                    title=eq["name"],
                    qty=qty,
                    unit_price_client=eq["daily_price"],
                    equipment_id=eq["id"],
                    is_subrental=False,
                    unit_cost_subrental=0,
                )

            recalc_quote_totals(qid)
            q = get_last_quote()
            items = get_quote_items(qid)
            await message.answer(fmt_quote(q, items))
            return

        if uid in FORM_QUOTE:
            step = FORM_QUOTE[uid]["step"]

            if step == "project":
                FORM_QUOTE[uid]["project_name"] = None if txt == "-" else txt
                FORM_QUOTE[uid]["step"] = "renter"
                await message.answer("Арендатор")
                return

            if step == "renter":
                FORM_QUOTE[uid]["renter_display_name"] = txt
                get_or_create_renter(txt, None)
                FORM_QUOTE[uid]["step"] = "date"
                await message.answer("Дата ДД.ММ.ГГГГ")
                return

            if step == "date":
                FORM_QUOTE[uid]["load_date"] = parse_date(txt)
                FORM_QUOTE[uid]["step"] = "time"
                await message.answer("Время ЧЧ:ММ")
                return

            if step == "time":
                FORM_QUOTE[uid]["load_time"] = parse_time(txt)
                FORM_QUOTE[uid]["step"] = "shifts"
                await message.answer("Смен")
                return

            if step == "shifts":
                FORM_QUOTE[uid]["shifts"] = int(txt)
                FORM_QUOTE[uid]["step"] = "return"
                await message.answer("Возврат ЧЧ:ММ или '-'")
                return

            if step == "return":
                FORM_QUOTE[uid]["return_time"] = None if txt == "-" else parse_time(txt)

                q = create_quote(
                    project_name=FORM_QUOTE[uid]["project_name"],
                    renter_display_name=FORM_QUOTE[uid]["renter_display_name"],
                    renter_full_name=None,
                    load_date=FORM_QUOTE[uid]["load_date"],
                    load_time=FORM_QUOTE[uid]["load_time"],
                    shifts=FORM_QUOTE[uid]["shifts"],
                    return_time=FORM_QUOTE[uid]["return_time"],
                    client_total=0,
                    subrental_total=0,
                )

                FORM_QUOTE.pop(uid)
                await message.answer(fmt_quote(q, []))
                return

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
