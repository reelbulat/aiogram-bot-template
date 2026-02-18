import asyncio
from aiogram import Bot, Dispatcher
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    @dp.message()
    async def start(message):
        await message.answer("Бот работает ✅")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
