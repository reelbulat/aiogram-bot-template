ALLOWED_USERS = {
    586702928,  # Булат
    384857319,  # Рифкат
}
import asyncio
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from sqlalchemy import text

from db import engine, init_db
from schema import create_tables
from crm import create_quote, get_last_quote, get_or_create_renter


BOT_TOKEN = os.getenv("BOT_TOKEN")

# Простая "форма" в памяти (на MVP ок, т.к. ты один админ)
FORM: dict[int, dict] = {}


def _parse_date(s: str):
    # ДД.ММ.ГГГГ
    return datetime.strptime(s.strip(), "%d.%m.%Y").date()


def _parse_time(s: str):
    # ЧЧ:ММ
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

    # База + таблицы
    init_db()
    create_tables()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # --- /db ---
    @dp.message(Command("db"))
    async def cmd_db(message: types.Message):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            await message.answer("База подключена ✅")
        except Exception as e:
            await message.answer(f"База НЕ подключена ❌\n{e}")

    # --- /start ---
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        await message.answer("Бот работает ✅\n\n" + _help_text())

    # --- /cancel ---
    @dp.message(Command("cancel"))
    async def cmd_cancel(message: types.Message):
        uid = message.from_user.id
        if uid in FORM:
            del FORM[uid]
        await message.answer("Ок, отменил ввод ✅\n\n" + _help_text())

    # --- /last ---
    @dp.message(Command("last"))
    async def cmd_last(message: types.Message):
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
            f"Статус: {q['status']}\n\n"
            + _help_text()
        )

    # --- /new ---
    @dp.message(Command("new"))
    async def cmd_new(message: types.Message):
        uid = message.from_user.id
        FORM[uid] = {"step": "project"}
        await message.answer(
            "Новая смета.\n"
            "1/8 Название проекта (или '-' если без названия)."
        )

    # --- общий обработчик (форма + обычный режим) ---
    @dp.message()
    async def any_message(message: types.Message):
        uid = message.from_user.id
        text_in = (message.text or "").strip()

        # если не в форме — просто подсказка
        if uid not in FORM:
            await message.answer("Ок.\n\n" + _help_text())
            return

        step = FORM[uid].get("step")

        try:
            # 1) project_name
            if step == "project":
                FORM[uid]["project_name"] = None if text_in == "-" else text_in
                FORM[uid]["step"] = "renter"
                await message.answer("2/8 Арендатор (как ты его называешь: фамилия/имя).")
                return

            # 2) renter display name (+ проверим/создадим)
            if step == "renter":
                FORM[uid]["renter_display_name"] = text_in

                # создаём если нет (пока без телефонов/ссылок)
                renter_id = get_or_create_renter(text_in, None)
                FORM[uid]["renter_id"] = renter_id

                FORM[uid]["step"] = "renter_full"
                await message.answer(
                    "3/8 Полное ФИО арендатора (если новый) или '-' если не нужно."
                )
                return

            # 3) renter full name
            if step == "renter_full":
                FORM[uid]["renter_full_name"] = None if text_in == "-" else text_in
                FORM[uid]["step"] = "load_date"
                await message.answer("4/8 Дата погрузки (ДД.ММ.ГГГГ), например 15.02.2026")
                return

            # 4) load_date
            if step == "load_date":
                FORM[uid]["load_date"] = _parse_date(text_in)
                FORM[uid]["step"] = "load_time"
                await message.answer("5/8 Время погрузки (ЧЧ:ММ), например 07:00")
                return

            # 5) load_time
            if step == "load_time":
                FORM[uid]["load_time"] = _parse_time(text_in)
                FORM[uid]["step"] = "shifts"
                await message.answer("6/8 Количество смен (целое число), например 1")
                return

            # 6) shifts
            if step == "shifts":
                shifts = int(text_in)
                if shifts <= 0:
                    raise ValueError("Количество смен должно быть > 0")
                FORM[uid]["shifts"] = shifts
                FORM[uid]["step"] = "return_time"
                await message.answer("7/8 Время возврата (ЧЧ:ММ) или '-' если неизвестно/пропуск")
                return

            # 7) return_time
            if step == "return_time":
                FORM[uid]["return_time"] = None if text_in == "-" else _parse_time(text_in)
                FORM[uid]["step"] = "client_total"
                await message.answer("8/8 Сумма клиенту (число ₽), например 10000")
                return

            # 8) client_total -> subrental_total -> create quote
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

                # закрываем форму
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
                    f"Статус: draft\n\n"
                    + _help_text()
                )
                return

            # если шаг неизвестный — сброс
            del FORM[uid]
            await message.answer("Форма сломалась, я сбросил её. Попробуй /new заново.")
            return

        except Exception as e:
            # оставляем пользователя на том же шаге
            await message.answer(f"Ошибка ввода: {e}\nПовтори сообщение на этом шаге или /cancel.")
            return

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
