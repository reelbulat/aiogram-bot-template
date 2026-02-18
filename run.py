import asyncio
import os
import re
from datetime import datetime
from typing import Optional

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

# 🔒 ДОСТУП ТОЛЬКО ЭТИМ TELEGRAM ID
ALLOWED_USERS = {
    586702928,  # Булат
    384857319,  # Рифкат
}

BOT_TOKEN = os.getenv("BOT_TOKEN")

# состояния "форм"
FORM_QUOTE: dict[int, dict] = {}
FORM_ITEMS: dict[int, int] = {}     # user_id -> quote_id
FORM_EQUIP: dict[int, dict] = {}


# ---------------- utils ----------------

def allowed(message: types.Message) -> bool:
    return bool(message.from_user) and (message.from_user.id in ALLOWED_USERS)


def parse_date(s: str):
    return datetime.strptime(s.strip(), "%d.%m.%Y").date()


def parse_time(s: str):
    return datetime.strptime(s.strip(), "%H:%M").time()


def status_badge(status: str) -> str:
    s = (status or "draft").lower()
    m = {
        "draft": "🟡 draft",
        "confirmed": "🟢 confirmed",
        "done": "🔵 done",
        "cancelled": "🔴 cancelled",
    }
    return m.get(s, "🟡 draft")


def fmt_quote(q: dict, items: Optional[list[dict]] = None) -> str:
    title = q.get("project_name") or q.get("renter_display_name") or "—"

    lines = [
        f"{title} — #{q['quote_number']}",
        f"Дата: {q['load_date'].strftime('%d.%m.%Y') if hasattr(q['load_date'], 'strftime') else q['load_date']}",
        f"Время: {q['load_time'].strftime('%H:%M') if hasattr(q['load_time'], 'strftime') else q['load_time']}",
        f"Смен: {q['shifts']}",
    ]

    # возврат показываем только если есть
    if q.get("return_time"):
        rt = q["return_time"].strftime("%H:%M") if hasattr(q["return_time"], "strftime") else str(q["return_time"])
        lines.append(f"Возврат: {rt}")

    if items is not None:
        lines.append("")
        lines.append("Позиции техники:")
        if not items:
            lines.append("— пока пусто —")
        else:
            for it in items:
                qty = it.get("qty", 1)
                unit = it.get("unit_price_client", 0)
                title_it = it.get("title") or "—"
                # если вдруг у тебя появится субаренда в items — отобразим мягко
                if it.get("is_subrental"):
                    cost = it.get("unit_cost_subrental", 0)
                    lines.append(f"- {title_it} — {qty} шт — {unit} ₽ (субаренда, себест {cost} ₽)")
                else:
                    lines.append(f"- {title_it} — {qty} шт — {unit} ₽")

    lines += [
        "",
        f"Сумма клиента: {q.get('client_total', 0)} ₽",
        f"Субаренда: {q.get('subrental_total', 0)} ₽",
        f"Прибыль: {q.get('profit_total', 0)} ₽",
        f"Статус: {status_badge(q.get('status', 'draft'))}",
    ]
    return "\n".join(lines)


def help_text() -> str:
    return (
        "Команды:\n"
        "/new — новая смета\n"
        "/items — добавить технику в последнюю смету (списком)\n"
        "/last — последняя смета\n"
        "/equip_new — добавить позицию в каталог\n"
        "/equip_find <слово> — поиск по каталогу\n"
        "/db — проверка базы\n"
        "/cancel — отменить ввод\n"
    )


def parse_items_lines(text_block: str) -> list[tuple[str, int]]:
    """
    Варианты:
    - "600x 2шт"
    - "600x 2 шт"
    - "600x x2" / "600x х2"
    - "600x 2x"
    - "600x 2"
    - "F22x" (qty=1)
    """
    out: list[tuple[str, int]] = []
    for raw in text_block.splitlines():
        s0 = raw.strip()
        if not s0:
            continue

        s = s0.lower().replace("×", "x").replace("х", "x")
        qty = 1
        token = s

        # x2 в конце
        m = re.search(r"\bx\s*(\d+)\s*$", s)
        if m:
            qty = int(m.group(1))
            token = s[: m.start()].strip()
        else:
            # 2шт / 2 шт / 2x / 2 (в конце)
            m2 = re.search(r"(\d+)\s*(шт|x)?\s*$", s)
            if m2:
                qty = int(m2.group(1))
                token = s[: m2.start(1)].strip()

        token = token.strip()
        if not token:
            raise ValueError(f"Не понял позицию: '{s0}'")
        if qty <= 0:
            raise ValueError(f"Количество должно быть >0: '{s0}'")

        out.append((token, qty))
    return out


# ---------------- main ----------------

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    init_db()
    create_tables()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # -------- commands --------

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        if not allowed(message):
            return
        await message.answer("CRM бот работает ✅\n\n" + help_text())

    @dp.message(Command("db"))
    async def cmd_db(message: types.Message):
        if not allowed(message):
            return
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        await message.answer("База подключена ✅")

    @dp.message(Command("cancel"))
    async def cmd_cancel(message: types.Message):
        if not allowed(message):
            return
        uid = message.from_user.id
        FORM_QUOTE.pop(uid, None)
        FORM_ITEMS.pop(uid, None)
        FORM_EQUIP.pop(uid, None)
        await message.answer("Ок, отменил ввод ✅\n\n" + help_text())

    @dp.message(Command("last"))
    async def cmd_last(message: types.Message):
        if not allowed(message):
            return
        q = get_last_quote()
        if not q:
            await message.answer("Смет пока нет.\nСоздай: /new")
            return
        items = get_quote_items(q["id"])
        await message.answer(fmt_quote(q, items))

    @dp.message(Command("new"))
    async def cmd_new(message: types.Message):
        if not allowed(message):
            return
        uid = message.from_user.id
        FORM_QUOTE[uid] = {"step": "project"}
        await message.answer("1/6 Название проекта или '-' (если не нужно)")

    @dp.message(Command("items"))
    async def cmd_items(message: types.Message):
        if not allowed(message):
            return
        q = get_last_quote()
        if not q:
            await message.answer("Нет сметы. Сначала: /new")
            return
        FORM_ITEMS[message.from_user.id] = q["id"]
        await message.answer(
            "Пришли список техники (каждая строка — позиция):\n"
            "пример:\n"
            "600x 2шт\n"
            "F22x\n"
            "систенд 40 x4"
        )

    @dp.message(Command("equip_find"))
    async def cmd_equip_find(message: types.Message):
        if not allowed(message):
            return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Используй так: /equip_find <слово>")
            return
        key = parts[1].strip()
        # твой crm.py может не иметь поиска, поэтому используем alias поиск "как есть"
        eq = find_equipment_by_alias(key)
        if not eq:
            await message.answer(f"Не нашёл по алиасу: {key}\nДобавь: /equip_new")
            return
        await message.answer(
            f"Нашёл:\n{eq.get('name')}\nЦена/смена: {eq.get('daily_price')} ₽\nID: {eq.get('id')}"
        )

    @dp.message(Command("equip_new"))
    async def cmd_equip_new(message: types.Message):
        if not allowed(message):
            return
        uid = message.from_user.id
        FORM_EQUIP[uid] = {"step": "name"}
        await message.answer("Новая позиция в каталог.\n1/4 Полное название (например: Aputure LS 600x Pro)")

    # -------- text handler --------

    @dp.message()
    async def text_handler(message: types.Message):
        if not allowed(message):
            return

        uid = message.from_user.id
        txt = (message.text or "").strip()

        # --- режим /items ---
        if uid in FORM_ITEMS:
            qid = FORM_ITEMS.pop(uid)
            try:
                pairs = parse_items_lines(txt)
            except Exception as e:
                await message.answer(f"Не понял список. Ошибка: {e}\nПример:\n600x 2шт\nF22x\nсистенд 40 x4")
                return

            not_found: list[str] = []
            added = 0

            for token, qty in pairs:
                eq = find_equipment_by_alias(token)
                if not eq:
                    not_found.append(token)
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
                added += 1

            recalc_quote_totals(qid)
            q = get_last_quote()
            items = get_quote_items(qid)

            out = fmt_quote(q, items)

            if not_found:
                out += (
                    "\n\n⚠️ Не нашёл в каталоге:\n- "
                    + "\n- ".join(not_found)
                    + "\n\nДобавь: /equip_new\nили попробуй другой алиас."
                )

            if added == 0 and not_found:
                out += "\n\n(Ничего не добавил, потому что все позиции не найдены.)"

            await message.answer(out)
            return

        # --- режим /equip_new ---
        if uid in FORM_EQUIP:
            step = FORM_EQUIP[uid]["step"]

            if step == "name":
                FORM_EQUIP[uid]["name"] = txt
                FORM_EQUIP[uid]["step"] = "daily_price"
                await message.answer("2/4 Цена за смену (число ₽), например 5000")
                return

            if step == "daily_price":
                try:
                    FORM_EQUIP[uid]["daily_price"] = int(re.sub(r"\D", "", txt))
                except:
                    await message.answer("Нужно число. Пример: 5000")
                    return
                FORM_EQUIP[uid]["step"] = "purchase_price"
                await message.answer("3/4 Оценочная стоимость (число ₽), например 127900 (или 0 если неизвестно)")
                return

            if step == "purchase_price":
                try:
                    FORM_EQUIP[uid]["purchase_price"] = int(re.sub(r"\D", "", txt))
                except:
                    await message.answer("Нужно число. Пример: 127900 или 0")
                    return
                FORM_EQUIP[uid]["step"] = "aliases"
                await message.answer(
                    "4/4 Алиасы через запятую.\n"
                    "пример: 600x, 600х, 600 икс, aputure 600x"
                )
                return

            if step == "aliases":
                aliases = [a.strip().lower() for a in txt.split(",") if a.strip()]
                name = FORM_EQUIP[uid]["name"]
                daily_price = FORM_EQUIP[uid]["daily_price"]
                purchase_price = FORM_EQUIP[uid]["purchase_price"]

                # пытаемся вызвать add_equipment устойчиво к разным сигнатурам
                created = None
                try:
                    created = add_equipment(
                        name=name,
                        daily_price=daily_price,
                        purchase_price=purchase_price,
                        aliases=aliases,
                    )
                except TypeError:
                    try:
                        created = add_equipment(name, daily_price, purchase_price, aliases)
                    except TypeError:
                        try:
                            created = add_equipment(name=name, daily_price=daily_price, purchase_price=purchase_price)
                        except Exception as e:
                            FORM_EQUIP.pop(uid, None)
                            await message.answer(f"Не смог создать позицию. Ошибка: {e}")
                            return

                FORM_EQUIP.pop(uid, None)
                await message.answer(
                    f"Позиция добавлена ✅\n{name}\nЦена/смена: {daily_price} ₽\n"
                    f"Алиасы: {', '.join(aliases) if aliases else '—'}"
                )
                return

        # --- режим /new (создание сметы) ---
        if uid in FORM_QUOTE:
            step = FORM_QUOTE[uid]["step"]

            if step == "project":
                FORM_QUOTE[uid]["project_name"] = None if txt == "-" else txt
                FORM_QUOTE[uid]["step"] = "renter"
                await message.answer("2/6 Арендатор (имя/фамилия)")
                return

            if step == "renter":
                FORM_QUOTE[uid]["renter_display_name"] = txt

                # устойчивый вызов get_or_create_renter
                try:
                    get_or_create_renter(txt)
                except TypeError:
                    try:
                        get_or_create_renter(txt, None)
                    except:
                        pass

                FORM_QUOTE[uid]["step"] = "date"
                await message.answer("3/6 Дата погрузки (ДД.ММ.ГГГГ), например 20.02.2026")
                return

            if step == "date":
                try:
                    FORM_QUOTE[uid]["load_date"] = parse_date(txt)
                except:
                    await message.answer("Формат даты: ДД.ММ.ГГГГ (пример 20.02.2026)")
                    return
                FORM_QUOTE[uid]["step"] = "time"
                await message.answer("4/6 Время погрузки (ЧЧ:ММ), например 07:00")
                return

            if step == "time":
                try:
                    FORM_QUOTE[uid]["load_time"] = parse_time(txt)
                except:
                    await message.answer("Формат времени: ЧЧ:ММ (пример 07:00)")
                    return
                FORM_QUOTE[uid]["step"] = "shifts"
                await message.answer("5/6 Количество смен (целое число), например 1")
                return

            if step == "shifts":
                try:
                    FORM_QUOTE[uid]["shifts"] = int(re.sub(r"\D", "", txt))
                except:
                    await message.answer("Нужно число. Пример: 1")
                    return
                FORM_QUOTE[uid]["step"] = "return_time"
                await message.answer("6/6 Время возврата (ЧЧ:ММ) или '-' если неизвестно/пропуск")
                return

            if step == "return_time":
                if txt == "-":
                    rt = None
                else:
                    try:
                        rt = parse_time(txt)
                    except:
                        await message.answer("Формат времени возврата: ЧЧ:ММ или '-'")
                        return

                q = create_quote(
                    project_name=FORM_QUOTE[uid]["project_name"],
                    renter_display_name=FORM_QUOTE[uid]["renter_display_name"],
                    renter_full_name=None,
                    load_date=FORM_QUOTE[uid]["load_date"],
                    load_time=FORM_QUOTE[uid]["load_time"],
                    shifts=FORM_QUOTE[uid]["shifts"],
                    return_time=rt,
                    client_total=0,
                    subrental_total=0,
                )
                FORM_QUOTE.pop(uid, None)

                await message.answer("Смета создана ✅\n\n" + fmt_quote(q, items=[] ) + "\n\nДобавь технику: /items")
                return

        # --- fallback: если не в режиме ввода ---
        await message.answer(
            "Я отвечаю на ввод только в режимах:\n"
            "• /new — создание сметы\n"
            "• /items — добавление техники\n"
            "• /equip_new — новая позиция\n\n"
            + help_text()
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
