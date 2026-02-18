import asyncio
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from sqlalchemy import text

from db import engine, init_db
from schema import create_tables
from crm import create_quote, get_last_quote, get_or_create_renter


# ✅ Доступ только этим Telegram ID
ALLOWED_USERS = {
    586702928,  # Булат
    384857319,  # Рифкат
}

BOT_TOKEN = os.getenv("BOT_TOKEN")

# MVP-форма в памяти
FORM: dict[int, dict] = {}


def _is_allowed(message: types.Message) -> bool:
    return bool(message.from_user) and (message.from_user.id in ALLOWED_USERS)


def _parse_date(s: str):
    return datetime.strptime(s.strip(), "%d.%m.%Y").date()


def _parse_time(s: str):
    return datetime.strptime(s.strip(), "%H:%M").time()


def _help_text():
    return (
        "Команды:\n"
        "/new — новая смета\n"
        "/last — последняя смета\n"
        "/db — проверка базы\n"
        "/cancel — отменить ввод\n"
    )


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set in environment variables")

    init_db()
    create_tables()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # --- /start ---
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        if not _is_allowed(message):
            return
        await message.answer("CRM бот работает ✅\n\n" + _help_text())

    # --- /db ---
    @dp.message(Command("db"))
    async def cmd_db(message: types.Message):
        if not _is_allowed(message):
            return
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            await message.answer("База подключена ✅")
        except Exception as e:
            await message.answer(f"База НЕ подключена ❌\n{e}")

    # --- /cancel ---
    @dp.message(Command("cancel"))
    async def cmd_cancel(message: types.Message):
        if not _is_allowed(message):
            return
        uid = message.from_user.id
        if uid in FORM:
            del FORM[uid]
        await message.answer("Ок, отменил ввод ✅\n\n" + _help_text())

    # --- /last ---
    @dp.message(Command("last"))
    async def cmd_last(message: types.Message):
        if not _is_allowed(message):
            return
        q = get_last_quote()
        if not q:
            await message.answer("Смет пока нет.\n\n" + _help_text())
            return

        title = q["project_name"] or q["renter_display_name"]
        await message.answer(
            f"#{q['quote_number']} — {title}\n"
            f"Погрузка: {q['load_date']} {q['load_time']}\n"
            f"Смен: {q['shifts']}\n"
            f"Возврат: {q['return_time'] or '—'}\n\n"
            f"Сумма клиенту: {q['client_total']} ₽\n"
            f"Субаренда: {q['subrental_total']} ₽\n"
            f"Прибыль: {q['profit_total']} ₽\n"
            f"Статус: {q['status']}\n"
        )

    # --- /new ---
    @dp.message(Command("new"))
    async def cmd_new(message: types.Message):
        if not _is_allowed(message):
            return
        uid = message.from_user.id
        FORM[uid] = {"step": "project"}
        await message.answer("Новая смета.\n1/8 Название проекта (или '-' если без названия).")

    # --- общий обработчик (форма + обычный режим) ---
    @dp.message()
    async def any_message(message: types.Message):
        if not _is_allowed(message):
            return

        uid = message.from_user.id
        text_in = (message.text or "").strip()

        # Если не в форме — просто подсказка
        if uid not in FORM:
            await message.answer(_help_text())
            return

        step = FORM[uid].get("step")

        try:
            if step == "project":
                FORM[uid]["project_name"] = None if text_in == "-" else text_in
                FORM[uid]["step"] = "renter"
                await message.answer("2/8 Арендатор (как ты его называешь: фамилия/имя).")
                return

            if step == "renter":
                FORM[uid]["renter_display_name"] = text_in
                get_or_create_renter(text_in, None)
                FORM[uid]["step"] = "renter_full"
                await message.answer("3/8 Полное ФИО (если новый) или '-' если пропуск.")
                return

            if step == "renter_full":
                FORM[uid]["renter_full_name"] = None if text_in == "-" else text_in
                FORM[uid]["step"] = "load_date"
                await message.answer("4/8 Дата погрузки (ДД.ММ.ГГГГ), например 15.02.2026")
                return

            if step == "load_date":
                FORM[uid]["load_date"] = _parse_date(text_in)
                FORM[uid]["step"] = "load_time"
                await message.answer("5/8 Время погрузки (ЧЧ:ММ), например 07:00")
                return

            if step == "load_time":
                FORM[uid]["load_time"] = _parse_time(text_in)
                FORM[uid]["step"] = "shifts"
                await message.answer("6/8 Количество смен (целое число), например 1")
                return

            if step == "shifts":
                shifts = int(text_in)
                if shifts <= 0:
                    raise ValueError("Количество смен должно быть > 0")
                FORM[uid]["shifts"] = shifts
                FORM[uid]["step"] = "return_time"
                await message.answer("7/8 Время возврата (ЧЧ:ММ) или '-' если неизвестно/пропуск")
                return

            if step == "return_time":
                FORM[uid]["return_time"] = None if text_in == "-" else _parse_time(text_in)
                FORM[uid]["step"] = "client_total"
                await message.answer("8/8 Сумма клиенту (число ₽), например 10000")
                return

            if step == "client_total":
                FORM[uid]["client_total"] = int(text_in)
                FORM[uid]["step"] = "sub_total"
                await message.answer("Доп. шаг: Субаренда (сколько ты платишь другим). Число или 0")
                return

            if step == "sub_total":
                FORM[uid]["subrental_total"] = int(text_in)

                q = create_quote(
                    project_name=FORM[uid]["project_name"],
                    renter_display_name=FORM[uid]["renter_display_name"],
                    renter_full_name=FORM[uid]["renter_full_name"],
                    load_date=FORM[uid]["load_date"],
                    load_time=FORM[uid]["load_time"],
                    shifts=FORM[uid]["shifts"],
                    return_time=FORM[uid]["return_time"],
                    client_total=FORM[uid]["client_total"],
                    subrental_total=FORM[uid]["subrental_total"],
                )

                del FORM[uid]

                title = q["project_name"] or q["renter_display_name"]
                await message.answer(
                    "Смета создана ✅\n"
                    f"#{q['quote_number']} — {title}\n"
                    f"Погрузка: {q['load_date']} {q['load_time']}\n"
                    f"Смен: {q['shifts']}\n"
                    f"Возврат: {q['return_time'] or '—'}\n\n"
                    f"Сумма клиенту: {q['client_total']} ₽\n"
                    f"Субаренда: {q['subrental_total']} ₽\n"
                    f"Прибыль: {q['profit_total']} ₽\n"
                    f"Статус: draft\n"
                )
                return

            # если шаг неизвестный — сброс
            del FORM[uid]
            await message.answer("Форма сброшена. Попробуй /new заново.")
            return

        except Exception as e:
            await message.answer(f"Ошибка ввода: {e}\nПовтори на этом шаге или /cancel.")
            return

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
