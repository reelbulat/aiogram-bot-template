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


# 🔒 ДОСТУП ТОЛЬКО ЭТИМ TELEGRAM ID
ALLOWED_USERS = {
    586702928,  # Булат
    384857319,  # Рифкат
}

BOT_TOKEN = os.getenv("BOT_TOKEN")

# формы (MVP)
FORM_QUOTE: dict[int, dict] = {}
FORM_EQUIP: dict[int, dict] = {}
FORM_ITEMS: dict[int, dict] = {}  # режим добавления позиций в последнюю смету


def allowed(message: types.Message) -> bool:
    return bool(message.from_user) and (message.from_user.id in ALLOWED_USERS)


def parse_date(s: str):
    return datetime.strptime(s.strip(), "%d.%m.%Y").date()


def parse_time(s: str):
    return datetime.strptime(s.strip(), "%H:%M").time()


def help_text() -> str:
    return (
        "Команды:\n"
        "/new — новая смета\n"
        "/last — последняя смета\n"
        "/items — добавить технику в последнюю смету (списком)\n"
        "/equip_new — создать позицию в каталоге\n"
        "/equip_find <слово> — найти позицию\n"
        "/db — проверка базы\n"
        "/cancel — отменить ввод\n"
    )


def fmt_quote(q: dict, items: list[dict] | None = None) -> str:
    title = q.get("project_name") or q.get("renter_display_name") or "—"
    lines = [
        f"#{q['quote_number']} — {title}",
        f"Погрузка: {q['load_date']} {q['load_time']}",
        f"Смен: {q['shifts']}",
        f"Возврат: {q['return_time'] or '—'}",
    ]

    if items is not None:
        lines.append("")
        lines.append("Состав:")
        if not items:
            lines.append("— пока пусто —")
        else:
            for it in items:
                qty = it["qty"]
                unit = it["unit_price_client"]
                sub = it["is_subrental"]
                cost = it["unit_cost_subrental"]
                if sub:
                    lines.append(f"- {qty}× {it['title']} — {unit} ₽ (субаренда, себест {cost} ₽)")
                else:
                    lines.append(f"- {qty}× {it['title']} — {unit} ₽")

    lines += [
        "",
        f"Сумма клиенту: {q.get('client_total', 0)} ₽",
        f"Субаренда: {q.get('subrental_total', 0)} ₽",
        f"Прибыль: {q.get('profit_total', 0)} ₽",
        f"Статус: {q.get('status', 'draft')}",
    ]
    return "\n".join(lines)


def parse_items_lines(text_block: str) -> list[tuple[str, int]]:
    """
    Принимаем блок строк:
    600x 2
    систенд 40 4
    фрост 1
    Если qty не указан — считаем 1.
    Возвращаем список (token, qty)
    """
    out = []
    for raw in text_block.splitlines():
        s = raw.strip()
        if not s:
            continue
        # ищем последнее число в строке как qty
        m = re.search(r"(\d+)\s*$", s)
        if m:
            qty = int(m.group(1))
            token = s[: m.start(1)].strip()
            if not token:
                token = s.strip()
        else:
            qty = 1
            token = s

        if qty <= 0:
            raise ValueError(f"qty должен быть >0: '{s}'")

        out.append((token, qty))
    return out


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    init_db()
    create_tables()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # -------- базовые команды --------

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        if not allowed(message):
            return
        await message.answer("CRM бот работает ✅\n\n" + help_text())

    @dp.message(Command("db"))
    async def cmd_db(message: types.Message):
        if not allowed(message):
            return
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            await message.answer("База подключена ✅")
        except Exception as e:
            await message.answer(f"База НЕ подключена ❌\n{e}")

    @dp.message(Command("cancel"))
    async def cmd_cancel(message: types.Message):
        if not allowed(message):
            return
        uid = message.from_user.id
        FORM_QUOTE.pop(uid, None)
        FORM_EQUIP.pop(uid, None)
        FORM_ITEMS.pop(uid, None)
        await message.answer("Ок, отменил ✅")

    @dp.message(Command("last"))
    async def cmd_last(message: types.Message):
        if not allowed(message):
            return
        q = get_last_quote()
        if not q:
            await message.answer("Смет пока нет.\n\n" + help_text())
            return
        items = get_quote_items(q["id"])
        await message.answer(fmt_quote(q, items))

    # -------- создание сметы (форма) --------

    @dp.message(Command("new"))
    async def cmd_new(message: types.Message):
        if not allowed(message):
            return
        uid = message.from_user.id
        FORM_QUOTE[uid] = {"step": "project"}
        await message.answer("Новая смета.\n1/8 Название проекта (или '-' если без названия).")

    # -------- каталог (создание позиции) --------

    @dp.message(Command("equip_new"))
    async def cmd_equip_new(message: types.Message):
        if not allowed(message):
            return
        uid = message.from_user.id
        FORM_EQUIP[uid] = {"step": "name"}
        await message.answer(
            "Новая позиция в каталоге.\n"
            "1/6 Полное название (например: Aputure LS 600x Pro)"
        )

    @dp.message(Command("equip_find"))
    async def cmd_equip_find(message: types.Message):
        if not allowed(message):
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Формат: /equip_find <слово/алиас>\nНапр: /equip_find 600x")
            return
        token = parts[1].strip()
        eq = find_equipment_by_alias(token)
        if not eq:
            await message.answer(f"Не нашёл по '{token}'.\nМожно создать: /equip_new")
            return
        await message.answer(
            f"Нашёл:\n"
            f"{eq['name']}\n"
            f"Категория: {eq['category']}\n"
            f"Цена/смена: {eq['daily_price']} ₽\n"
            f"Кол-во: {eq['qty_total']}\n"
            f"Статус: {eq['status']}"
        )

    # -------- добавление items в последнюю смету --------

    @dp.message(Command("items"))
    async def cmd_items(message: types.Message):
        if not allowed(message):
            return
        q = get_last_quote()
        if not q:
            await message.answer("Нет смет. Сначала создай /new")
            return
        uid = message.from_user.id
        FORM_ITEMS[uid] = {"quote_id": q["id"]}
        await message.answer(
            "Ок. Пришли списком позиции (каждая с новой строки).\n"
            "Формат: <алиас/название> <кол-во>\n"
            "Пример:\n"
            "600x 2\n"
            "систенд 40 4\n"
            "фрост 1\n\n"
            "Чтобы отменить: /cancel"
        )

    # -------- единый обработчик текста (формы) --------

    @dp.message()
    async def on_text(message: types.Message):
        if not allowed(message):
            return

        uid = message.from_user.id
        text_in = (message.text or "").strip()

        # --- режим добавления items ---
        if uid in FORM_ITEMS:
            qid = FORM_ITEMS[uid]["quote_id"]
            try:
                pairs = parse_items_lines(text_in)
            except Exception as e:
                await message.answer(f"Ошибка списка: {e}\nСкинь ещё раз или /cancel")
                return

            not_found = []
            added = 0

            for token, qty in pairs:
                eq = find_equipment_by_alias(token)
                if not eq:
                    not_found.append(token)
                    continue

                if eq["status"] == "ремонт":
                    not_found.append(f"{token} (в ремонте)")
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

            client_total, sub_total, profit_total = recalc_quote_totals(qid)

            # показ результата
            q = get_last_quote()  # последняя = текущая, пока MVP
            items = get_quote_items(qid)

            msg = []
            if added:
                msg.append(f"Добавил позиций: {added} ✅")
            if not_found:
                msg.append("Не нашёл/нельзя добавить:")
                msg.extend([f"- {x}" for x in not_found])
                msg.append("Создать новую позицию: /equip_new")

            msg.append("")
            msg.append(fmt_quote(q, items))

            FORM_ITEMS.pop(uid, None)
            await message.answer("\n".join(msg))
            return

        # --- форма создания сметы ---
        if uid in FORM_QUOTE:
            step = FORM_QUOTE[uid].get("step")
            try:
                if step == "project":
                    FORM_QUOTE[uid]["project_name"] = None if text_in == "-" else text_in
                    FORM_QUOTE[uid]["step"] = "renter"
                    await message.answer("2/8 Арендатор (фамилия/имя).")
                    return

                if step == "renter":
                    FORM_QUOTE[uid]["renter_display_name"] = text_in
                    get_or_create_renter(text_in, None)
                    FORM_QUOTE[uid]["step"] = "renter_full"
                    await message.answer("3/8 Полное ФИО арендатора или '-' (пропуск).")
                    return

                if step == "renter_full":
                    FORM_QUOTE[uid]["renter_full_name"] = None if text_in == "-" else text_in
                    FORM_QUOTE[uid]["step"] = "load_date"
                    await message.answer("4/8 Дата погрузки ДД.ММ.ГГГГ (например 15.02.2026)")
                    return

                if step == "load_date":
                    FORM_QUOTE[uid]["load_date"] = parse_date(text_in)
                    FORM_QUOTE[uid]["step"] = "load_time"
                    await message.answer("5/8 Время погрузки ЧЧ:ММ (например 07:00)")
                    return

                if step == "load_time":
                    FORM_QUOTE[uid]["load_time"] = parse_time(text_in)
                    FORM_QUOTE[uid]["step"] = "shifts"
                    await message.answer("6/8 Количество смен (целое число), например 1")
                    return

                if step == "shifts":
                    shifts = int(text_in)
                    if shifts <= 0:
                        raise ValueError("Смен должно быть > 0")
                    FORM_QUOTE[uid]["shifts"] = shifts
                    FORM_QUOTE[uid]["step"] = "return_time"
                    await message.answer("7/8 Время возврата ЧЧ:ММ или '-' (пропуск)")
                    return

                if step == "return_time":
                    FORM_QUOTE[uid]["return_time"] = None if text_in == "-" else parse_time(text_in)
                    FORM_QUOTE[uid]["step"] = "client_total"
                    await message.answer("8/8 Сумма клиенту (число ₽), например 10000")
                    return

                if step == "client_total":
                    FORM_QUOTE[uid]["client_total"] = int(text_in)
                    FORM_QUOTE[uid]["step"] = "sub_total"
                    await message.answer("Доп. шаг: Субаренда (сколько ты платишь другим). Число или 0")
                    return

                if step == "sub_total":
                    FORM_QUOTE[uid]["subrental_total"] = int(text_in)

                    q = create_quote(
                        project_name=FORM_QUOTE[uid]["project_name"],
                        renter_display_name=FORM_QUOTE[uid]["renter_display_name"],
                        renter_full_name=FORM_QUOTE[uid]["renter_full_name"],
                        load_date=FORM_QUOTE[uid]["load_date"],
                        load_time=FORM_QUOTE[uid]["load_time"],
                        shifts=FORM_QUOTE[uid]["shifts"],
                        return_time=FORM_QUOTE[uid]["return_time"],
                        client_total=FORM_QUOTE[uid]["client_total"],
                        subrental_total=FORM_QUOTE[uid]["subrental_total"],
                    )

                    FORM_QUOTE.pop(uid, None)

                    await message.answer(
                        "Смета создана ✅\n\n"
                        + fmt_quote(q, items=[])
                        + "\n\nТеперь добавь технику: /items"
                    )
                    return

                # fallback
                FORM_QUOTE.pop(uid, None)
                await message.answer("Форма сброшена. /new")
                return

            except Exception as e:
                await message.answer(f"Ошибка ввода: {e}\nПовтори на этом шаге или /cancel")
                return

        # --- форма создания позиции каталога ---
        if uid in FORM_EQUIP:
            step = FORM_EQUIP[uid].get("step")
            try:
                if step == "name":
                    FORM_EQUIP[uid]["name"] = text_in
                    FORM_EQUIP[uid]["step"] = "category"
                    await message.answer(
                        "2/6 Категория (строго одно):\n"
                        "camera / lens / media / light_head / grip / other"
                    )
                    return

                if step == "category":
                    cat = text_in.strip()
                    if cat not in {"camera", "lens", "media", "light_head", "grip", "other"}:
                        raise ValueError("Категория должна быть одной из: camera,lens,media,light_head,grip,other")
                    FORM_EQUIP[uid]["category"] = cat
                    FORM_EQUIP[uid]["step"] = "daily_price"
                    await message.answer("3/6 Цена за смену (число ₽), например 5000")
                    return

                if step == "daily_price":
                    FORM_EQUIP[uid]["daily_price"] = int(text_in)
                    FORM_EQUIP[uid]["step"] = "purchase_price"
                    await message.answer("4/6 Оценочная стоимость (число ₽) или '-' если нет")
                    return

                if step == "purchase_price":
                    FORM_EQUIP[uid]["purchase_price"] = None if text_in == "-" else int(text_in)
                    FORM_EQUIP[uid]["step"] = "qty"
                    await message.answer("5/6 Количество на складе (число), например 2")
                    return

                if step == "qty":
                    FORM_EQUIP[uid]["qty_total"] = int(text_in)
                    FORM_EQUIP[uid]["step"] = "aliases"
                    await message.answer(
                        "6/6 Алиасы через запятую (как ты пишешь в смете), например:\n"
                        "600x, 600 икс, апутур 600x"
                    )
                    return

                if step == "aliases":
                    aliases = text_in
                    eid = add_equipment(
                        name=FORM_EQUIP[uid]["name"],
                        category=FORM_EQUIP[uid]["category"],
                        daily_price=FORM_EQUIP[uid]["daily_price"],
                        purchase_price=FORM_EQUIP[uid]["purchase_price"],
                        qty_total=FORM_EQUIP[uid]["qty_total"],
                        status="ок",
                        aliases=aliases,
                    )
                    FORM_EQUIP.pop(uid, None)
                    await message.answer(f"Позиция создана ✅ (id={eid})\nТеперь можешь /equip_find 600x или /items")
                    return

                FORM_EQUIP.pop(uid, None)
                await message.answer("Форма каталога сброшена. /equip_new")
                return

            except Exception as e:
                await message.answer(f"Ошибка: {e}\nПовтори на этом шаге или /cancel")
                return

        # --- обычный режим ---
        await message.answer(help_text())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
