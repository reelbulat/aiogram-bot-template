from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.db.base import SessionLocal
from app.services.inventory_service import (
    create_equipment_model,
    get_model_by_id,
    search_models,
    update_equipment_model,
)
from app.states import AddModelFlow, EditModelFlow, FindModelFlow
from app.utils.formatters import format_model_card
from app.utils.validators import parse_money

router = Router()


@router.message(Command("addmodel"))
async def cmd_addmodel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddModelFlow.name)
    await message.answer("Полное название модели:")


@router.message(AddModelFlow.name)
async def addmodel_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(AddModelFlow.category)
    await message.answer("Категория:")


@router.message(AddModelFlow.category)
async def addmodel_category(message: Message, state: FSMContext) -> None:
    await state.update_data(category=message.text.strip())
    await state.set_state(AddModelFlow.daily_rent_price)
    await message.answer("Цена аренды за смену:")


@router.message(AddModelFlow.daily_rent_price)
async def addmodel_price(message: Message, state: FSMContext) -> None:
    try:
        daily_rent_price = parse_money(message.text)
    except Exception:
        await message.answer("Неверная сумма.")
        return

    await state.update_data(daily_rent_price=daily_rent_price)
    await state.set_state(AddModelFlow.estimated_value)
    await message.answer("Оценочная стоимость:")


@router.message(AddModelFlow.estimated_value)
async def addmodel_estimated_value(message: Message, state: FSMContext) -> None:
    try:
        estimated_value = parse_money(message.text)
    except Exception:
        await message.answer("Неверная сумма.")
        return

    await state.update_data(estimated_value=estimated_value)

    data = await state.get_data()
    preview = (
        f"Проверь модель:\n\n"
        f"Название: {data['name']}\n"
        f"Категория: {data['category']}\n"
        f"Цена аренды: {data['daily_rent_price']}\n"
        f"Оценочная стоимость: {data['estimated_value']}\n\n"
        f"Напиши: yes"
    )

    await state.set_state(AddModelFlow.confirm)
    await message.answer(preview)


@router.message(AddModelFlow.confirm)
async def addmodel_confirm(message: Message, state: FSMContext) -> None:
    if message.text.strip().lower() != "yes":
        await message.answer("Подтверждение не получено. Напиши yes.")
        return

    data = await state.get_data()

    with SessionLocal() as db:
        try:
            model = create_equipment_model(
                db=db,
                name=data["name"],
                category=data["category"],
                daily_rent_price=data["daily_rent_price"],
                estimated_value=data["estimated_value"],
            )
        except ValueError as e:
            await message.answer(str(e))
            return

    await state.clear()
    await message.answer("Модель добавлена.\n\n" + format_model_card(model))


@router.message(Command("findmodel"))
async def cmd_findmodel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(FindModelFlow.query)
    await message.answer("Введи название модели для поиска:")


@router.message(FindModelFlow.query)
async def findmodel_query(message: Message, state: FSMContext) -> None:
    query = message.text.strip()

    with SessionLocal() as db:
        results = search_models(db, query=query, include_inactive=True, limit=5)

    if not results:
        await message.answer("Ничего не найдено.")
        await state.clear()
        return

    if len(results) == 1:
        await message.answer(format_model_card(results[0]))
        await state.clear()
        return

    text = "Нашёл несколько вариантов:\n\n"
    for i, model in enumerate(results, start=1):
        text += f"{i}. {model.name}\n"

    text += "\nНапиши точнее название модели."
    await message.answer(text)


@router.message(Command("editmodel"))
async def cmd_editmodel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(EditModelFlow.query)
    await message.answer("Введи название модели, которую нужно изменить:")


@router.message(EditModelFlow.query)
async def editmodel_query(message: Message, state: FSMContext) -> None:
    query = message.text.strip()

    with SessionLocal() as db:
        results = search_models(db, query=query, include_inactive=True, limit=5)

    if not results:
        await message.answer("Модель не найдена.")
        return

    if len(results) > 1:
        text = "Найдено несколько вариантов:\n\n"
        for i, model in enumerate(results, start=1):
            text += f"{i}. {model.name}\n"
        text += "\nНапиши точнее название модели."
        await message.answer(text)
        return

    model = results[0]

    await state.update_data(model_id=model.id)
    await state.set_state(EditModelFlow.field)

    text = (
        f"{format_model_card(model)}\n\n"
        f"Что изменить?\n"
        f"1 — Название\n"
        f"2 — Категория\n"
        f"3 — Цена аренды\n"
        f"4 — Оценочная стоимость"
    )
    await message.answer(text)


@router.message(EditModelFlow.field)
async def editmodel_field(message: Message, state: FSMContext) -> None:
    value = message.text.strip()

    if value not in {"1", "2", "3", "4"}:
        await message.answer("Введи 1, 2, 3 или 4.")
        return

    await state.update_data(field=value)
    await state.set_state(EditModelFlow.value)

    prompts = {
        "1": "Введи новое название:",
        "2": "Введи новую категорию:",
        "3": "Введи новую цену аренды:",
        "4": "Введи новую оценочную стоимость:",
    }

    await message.answer(prompts[value])


@router.message(EditModelFlow.value)
async def editmodel_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    model_id = data["model_id"]
    field = data["field"]
    raw_value = message.text.strip()

    kwargs = {}

    try:
        if field == "1":
            kwargs["name"] = raw_value
        elif field == "2":
            kwargs["category"] = raw_value
        elif field == "3":
            kwargs["daily_rent_price"] = parse_money(raw_value)
        elif field == "4":
            kwargs["estimated_value"] = parse_money(raw_value)
    except Exception:
        await message.answer("Неверное значение.")
        return

    with SessionLocal() as db:
        try:
            model = update_equipment_model(db, model_id=model_id, **kwargs)
        except ValueError as e:
            await message.answer(str(e))
            return

        if not model:
            await message.answer("Модель не найдена.")
            await state.clear()
            return

        model = get_model_by_id(db, model_id)

    await state.clear()
    await message.answer("Модель обновлена.\n\n" + format_model_card(model))
