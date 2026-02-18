import asyncio
import os

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from sqlalchemy import text

from db import engine, init_db
from schema import create_tables


BOT_TOKEN = os.getenv("BOT_TOKEN")


async def main():
    # 1) Проверка наличия токена
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set in environment variables")

    # 2) Подключение к БД + создание таблиц
    init_db()
    create_tables()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # /db — проверка соединения с Postgres
    @dp.message(Command("db"))
    async def cmd_db(message: types.Message):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            await message.answer("База подключена ✅")
        except Exception as e:
            await message.answer(f"База НЕ подключена ❌\n{e}")

    # /start — просто ответ
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        await message.answer("Бот работает ✅\nПроверка базы: /db")

    # Любые остальные сообщения
    @dp.message()
    async def any_message(message: types.Message):
        await message.answer("Бот работает ✅\nПроверка базы: /db")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
