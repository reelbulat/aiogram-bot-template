from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.catalog import REAL_CATALOG
from app.db.base import SessionLocal
from app.db.models import EquipmentModel

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer("Бот запущен.")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Текущее действие сброшено.")


@router.message(Command("seed"))
async def cmd_seed(message: Message) -> None:
    added = 0

    with SessionLocal() as db:
        for row in REAL_CATALOG:
            exists = (
                db.query(EquipmentModel)
                .filter(EquipmentModel.name.ilike(row["name"]))
                .first()
            )
            if exists:
                continue

            model = EquipmentModel(
                name=row["name"],
                category=row["category"],
                daily_rent_price=row["daily_rent_price"],
                estimated_value=row["estimated_value"],
                aliases=[],
            )
            db.add(model)
            added += 1

        db.commit()

    await message.answer(f"Каталог загружен. Добавлено позиций: {added}")
