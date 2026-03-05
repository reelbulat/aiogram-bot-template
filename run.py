import asyncio
import os
import re
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

from sqlalchemy import text
from db import init_db, engine
from schema import create_tables


ALLOWED_USERS = {586702928, 384857319}

STATUS_EMOJI = {
    "draft": "🟡",
    "confirmed": "🟢",
    "done": "🔵",
    "cancelled": "🔴",
}

BOT_TOKEN = os.getenv("BOT_TOKEN")


def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_USERS


async def deny_if_not_allowed(message: types.Message) -> bool:
    if not is_allowed(message.from_user.id):
        # важно: не палим, что бот существует
        return True
    return False


def parse_date_ddmmyyyy(s: str) -> Optional[str]:
    s = s.strip()
    try:
        dt = datetime.strptime(s, "%d.%m.%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_time_hhmm(s: str) -> Optional[str]:
    s = s.strip()
    try:
        dt = datetime.strptime(s, "%H:%M")
        return dt.strftime("%H:%M")
    except ValueError:
        return None


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def parse_items_text(text_block: str) -> list[str]:
    return [ln.strip() for ln in text_block.splitlines() if ln.strip()]


def money_int(s: str) -> Optional[int]:
    s = s.strip().replace("₽", "").replace(" ", "")
    if s in {"-", ""}:
        return None
    if not re.fullmatch(r"-?\d+", s):
        return None
    return int(s)


def render_quote_card(q: dict) -> str:
    status = q.get("status", "draft")
    st = f"{STATUS_EMOJI.get(status, '🟡')} {status}"

    title = q.get("title") or q.get("renter_name") or "—"
    number = q.get("number", "00000")

    date_s = q.get("load_date", "")
    time_s = q.get("load_time", "")
    shifts = q.get("shifts", "")

    ret = q.get("return_time")
    ret_line = f"\nВозврат: {ret}" if ret else ""

    items_block = q.get("items_text") or "— пока пусто —"

    client_sum = int(q.get("client_sum") or 0)
    subrent_sum = int(q.get("subrent_sum") or 0)
    profit = int(q.get("profit") or (client_sum - subrent_sum))

    return (
        f"Смета ✅\n\n"
        f"{title} — #{str(number).zfill(5)}\n"
        f"Дата: {date_s}\n"
        f"Время: {time_s}\n"
        f"Смен: {shifts}"
        f"{ret_line}\n\n"
        f"Позиции техники:\n{items_block}\n\n"
        f"Сумма клиента: {client_sum} ₽\n"
        f"Субаренда: {subrent_sum} ₽\n"
        f"Прибыль: {profit} ₽\n"
        f"Статус: {st}"
    )


class QuoteFlow(StatesGroup):
    title = State()
    renter = State()
    load_date = State()
    load_time = State()
    shifts = State()
    return_time = State()
    items = State()
    client_sum = State()
    subrent_sum = State()


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing in env vars")

    init_db()
    create_tables()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    from crm import (
        create_quote,
        get_last_quote,
        get_or_create_renter,
        resolve_items,
        attach_items_to_quote,
        finalize_money,
    )

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        if await deny_if_not_allowed(message):
            return
        await message.answer(
            "CRM бот работает ✅\n\n"
            "Команды:\n"
            "/new — новая смета\n"
            "/items — добавить/заменить список техники в текущей смете\n"
            "/last — последняя смета\n"
            "/db — проверка базы\n"
            "/cancel — отменить ввод\n"
        )

    @dp.message(Command("db"))
    async def cmd_db(message: types.Message):
        if await deny_if_not_allowed(message):
            return
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            await message.answer("База подключена ✅")
        except Exception as e:
            await message.answer(f"База НЕ подключена ❌\n{type(e).__name__}: {e}")

    @dp.message(Command("last"))
    async def cmd_last(message: types.Message):
        if await deny_if_not_allowed(message):
            return
        q = get_last_quote()
        if not q:
            await message.answer("Смет пока нет.")
            return
        await message.answer(render_quote_card(q))

    @dp.message(Command("cancel"))
    async def cmd_cancel(message: types.Message, state: FSMContext):
        if await deny_if_not_allowed(message):
            return
        await state.clear()
        await message.answer("Ок, ввод отменён.")

    @dp.message(Command("new"))
    async def cmd_new(message: types.Message, state: FSMContext):
        if await deny_if_not_allowed(message):
            return
        await state.clear()
        await state.set_state(QuoteFlow.title)
        await message.answer("1/8 Название проекта или '-' (если не нужно)")

    @dp.message(QuoteFlow.title, F.text)
    async def step_title(message: types.Message, state: FSMContext):
        if await deny_if_not_allowed(message):
            return
        title = normalize_spaces(message.text)
        if title == "-":
            title = ""
        await state.update_data(title=title)
        await state.set_state(QuoteFlow.renter)
        await message.answer("2/8 Арендатор (имя/фамилия)")

    @dp.message(QuoteFlow.renter, F.text)
    async def step_renter(message: types.Message, state: FSMContext):
        if await deny_if_not_allowed(message):
            return
        name = normalize_spaces(message.text)
        if not name:
            await message.answer("Имя арендатора не может быть пустым. Введи ещё раз.")
            return

        renter = get_or_create_renter(name)
        await state.update_data(renter_name=renter["name"], renter_id=renter["id"])
        await state.set_state(QuoteFlow.load_date)
        await message.answer("3/8 Дата погрузки (ДД.ММ.ГГГГ), например 21.03.2026")

    @dp.message(QuoteFlow.load_date, F.text)
    async def step_load_date(message: types.Message, state: FSMContext):
        if await deny_if_not_allowed(message):
            return
        d = parse_date_ddmmyyyy(message.text)
        if not d:
            await message.answer("Неверный формат. Нужно ДД.ММ.ГГГГ, например 21.03.2026")
            return
        await state.update_data(load_date=d)
        await state.set_state(QuoteFlow.load_time)
        await message.answer("4/8 Время погрузки (ЧЧ:ММ), например 07:00")

    @dp.message(QuoteFlow.load_time, F.text)
    async def step_load_time(message: types.Message, state: FSMContext):
        if await deny_if_not_allowed(message):
            return
        t = parse_time_hhmm(message.text)
        if not t:
            await message.answer("Неверный формат. Нужно ЧЧ:ММ, например 07:00")
            return
        await state.update_data(load_time=t)
        await state.set_state(QuoteFlow.shifts)
        await message.answer("5/8 Количество смен (целое число), например 1")

    @dp.message(QuoteFlow.shifts, F.text)
    async def step_shifts(message: types.Message, state: FSMContext):
        if await deny_if_not_allowed(message):
            return
        s = message.text.strip()
        if not re.fullmatch(r"\d+", s):
            await message.answer("Нужно целое число, например 1 или 2.")
            return
        shifts = int(s)
        if shifts <= 0:
            await message.answer("Смен должно быть >= 1.")
            return
        await state.update_data(shifts=shifts)
        await state.set_state(QuoteFlow.return_time)
        await message.answer("6/8 Время возврата (ЧЧ:ММ) или '-' если неизвестно/пропуск")

    @dp.message(QuoteFlow.return_time, F.text)
    async def step_return_time(message: types.Message, state: FSMContext):
        if await deny_if_not_allowed(message):
            return
        raw = message.text.strip()
        ret = None
        if raw != "-":
            ret = parse_time_hhmm(raw)
            if not ret:
                await message.answer("Неверный формат. Нужно ЧЧ:ММ или '-'")
                return

        await state.update_data(return_time=ret)
        data = await state.get_data()

        q = create_quote(
            title=data.get("title") or "",
            renter_id=data["renter_id"],
            renter_name=data["renter_name"],
            load_date=data["load_date"],
            load_time=data["load_time"],
            shifts=data["shifts"],
            return_time=data.get("return_time"),
            status="draft",
        )
        await state.update_data(quote_id=q["id"], quote_number=q["number"])

        await state.set_state(QuoteFlow.items)
        await message.answer(
            "7/8 Пришли список техники (каждая строка — позиция):\n"
            "пример:\n"
            "600x 2шт\n"
            "F22x\n"
            "систенд 40 x4\n\n"
            "Можно одним сообщением."
        )

    @dp.message(Command("items"))
    async def cmd_items(message: types.Message, state: FSMContext):
        if await deny_if_not_allowed(message):
            return
        data = await state.get_data()
        if "quote_id" not in data:
            await message.answer("Сначала создай смету: /new")
            return
        await state.set_state(QuoteFlow.items)
        await message.answer(
            "Пришли список техники (каждая строка — позиция):\n"
            "пример:\n"
            "600x 2шт\n"
            "F22x\n"
            "систенд 40 x4"
        )

    @dp.message(QuoteFlow.items, F.text)
    async def step_items(message: types.Message, state: FSMContext):
        if await deny_if_not_allowed(message):
            return
        data = await state.get_data()
        quote_id = data.get("quote_id")
        if not quote_id:
            await message.answer("Сначала создай смету: /new")
            return

        lines = parse_items_text(message.text)
        if not lines:
            await message.answer("Список пустой. Пришли хотя бы 1 строку.")
            return

        items, not_found, items_sum = resolve_items(lines)

        if not items:
            nf = "\n".join(f"- {x}" for x in (not_found or lines))
            await message.answer(
                "⚠️ Ничего не добавил, потому что позиции не найдены.\n\n"
                f"Не нашёл:\n{nf}\n\n"
                "Сначала засеем номенклатуру в equipment, потом будет находить по алиасам."
            )
            return

        attach_items_to_quote(int(quote_id), items)

        msg = "Техника добавлена ✅"
        if not_found:
            nf = "\n".join(f"- {x}" for x in not_found)
            msg += f"\n\n⚠️ Не нашёл в каталоге:\n{nf}"

        await state.update_data(items_sum=items_sum)
        await state.set_state(QuoteFlow.client_sum)
        await message.answer(
            msg
            + "\n\n8/8 Сумма клиенту (₽).\n"
            f"По умолчанию посчитал: {items_sum} ₽\n"
            "Отправь:\n"
            "- число (например 15000) чтобы заменить\n"
            "- '-' или '0' чтобы оставить как есть"
        )

    @dp.message(QuoteFlow.client_sum, F.text)
    async def step_client_sum(message: types.Message, state: FSMContext):
        if await deny_if_not_allowed(message):
            return
        data = await state.get_data()
        quote_id = data.get("quote_id")
        if not quote_id:
            await message.answer("Сначала /new")
            return

        default_sum = int(data.get("items_sum") or 0)
        raw = message.text.strip()

        if raw in {"-", "0", ""}:
            client_sum = default_sum
        else:
            v = money_int(raw)
            if v is None or v < 0:
                await message.answer("Нужно число ₽, либо '-'/'0' чтобы оставить сумму по технике.")
                return
            client_sum = v

        await state.update_data(client_sum=client_sum)
        await state.set_state(QuoteFlow.subrent_sum)
        await message.answer("Доп. шаг: Субаренда (сколько ты платишь другим). Число или 0")

    @dp.message(QuoteFlow.subrent_sum, F.text)
    async def step_subrent(message: types.Message, state: FSMContext):
        if await deny_if_not_allowed(message):
            return
        data = await state.get_data()
        quote_id = data.get("quote_id")
        if not quote_id:
            await message.answer("Сначала /new")
            return

        v = money_int(message.text)
        if v is None:
            await message.answer("Нужно число (например 5000) или 0.")
            return
        if v < 0:
            await message.answer("Субаренда не может быть отрицательной.")
            return

        client_sum = int(data.get("client_sum") or 0)
        subrent_sum = int(v)

        finalize_money(int(quote_id), client_sum=client_sum, subrent_sum=subrent_sum)
        q = get_last_quote()

        await state.clear()
        await message.answer("Готово ✅\n\n" + render_quote_card(q))

    @dp.message(F.text)
    async def fallback(message: types.Message, state: FSMContext):
        if not is_allowed(message.from_user.id):
            return

        cur = await state.get_state()
        if cur:
            await message.answer("Я жду ввод по текущему шагу формы. Если хочешь выйти — /cancel")
            return

        await message.answer(
            "Команды:\n"
            "/new — новая смета\n"
            "/last — последняя смета\n"
            "/items — добавить технику в текущую смету\n"
            "/db — проверка базы\n"
            "/cancel — отменить ввод"
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
