from db import init_db
from schema import create_tables
import asyncio
from aiogram import Bot, Dispatcher
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def main():
    init_db()
    create_tables()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    @dp.message()
    async def start(message):
        await message.answer("Бот работает ✅")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
