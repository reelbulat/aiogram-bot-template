import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import BaseFilter
from aiogram.types import BotCommand, Message
from sqlalchemy import text

from app.config import ALLOWED_USERS, BOT_TOKEN
from app.db.base import Base, SessionLocal, engine
from app.db import models  # noqa: F401
from app.handlers.common import router as common_router
from app.handlers.orders import router as orders_router
from app.handlers.catalog import router as catalog_router
from app.services.inventory_service import sync_search_names


logging.basicConfig(level=logging.INFO)


class AllowedUserFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if not ALLOWED_USERS:
            return True
        if not message.from_user:
            return False
        return message.from_user.id in ALLOWED_USERS


async def set_main_menu(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="new", description="Новый заказ"),
        BotCommand(command="last", description="Последний заказ"),
        BotCommand(command="addmodel", description="Добавить модель"),
        BotCommand(command="findmodel", description="Найти модель"),
        BotCommand(command="editmodel", description="Изменить модель"),
        BotCommand(command="cancel", description="Сброс"),
    ]
    await bot.set_my_commands(commands)


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def ensure_schema_updates() -> None:
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE equipment_models ADD COLUMN IF NOT EXISTS search_name TEXT"
        ))
        conn.execute(text(
            "ALTER TABLE equipment_models ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"
        ))
        conn.execute(text(
            "UPDATE equipment_models SET search_name = '' WHERE search_name IS NULL"
        ))


def bootstrap_catalog_metadata() -> None:
    with SessionLocal() as db:
        sync_search_names(db)


async def main() -> None:
    create_tables()
    ensure_schema_updates()
    bootstrap_catalog_metadata()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    protected_router = Router()
    protected_router.message.filter(AllowedUserFilter())
    protected_router.include_router(common_router)
    protected_router.include_router(catalog_router)
    protected_router.include_router(orders_router)

    dp.include_router(protected_router)

    await set_main_menu(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
