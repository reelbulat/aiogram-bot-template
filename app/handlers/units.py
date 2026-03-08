from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db.base import SessionLocal
from app.services.unit_service import create_unit, resolve_single_model, search_units
from app.states import AddUnitFlow, FindUnitFlow
from app.utils.formatters import format_unit_card, format_units_list
from app.utils.validators import parse_money

router = Router()


def unit_dash_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="-", callback_data="unit_defects_dash")]
        ]
    )


@router.message(Command("addunit"))
async def cmd_addunit(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddUnitFlow.model_query)
    await message.answer("1/4 - Модель для нового юнита")


@router.message(AddUnitFlow.model_query)
async def addunit_model_query(message: Message, state: FSMContext) -> None:
    query = message.text.strip()

    with SessionLocal() as db:
        model = resolve_single_model(db, query)

    if not model:
        await message.answer("Не смог однозначно определить модель. Напиши точнее.")
        return

    await state.update_data(
        addunit_model_id=model.id,
        addunit_model_name=model.name,
        addunit_model_category=model.category,
    )
    await state.set_state(AddUnitFlow.purchase_price)
    await message.answer(
        f"2/4 - Модель: {model.name}\n"
        f"Категория: {model.category}\n"
        "Укажите закупочную цену:"
    )


@router.message(AddUnitFlow.purchase_price)
async def addunit_purchase_price(message: Message, state: FSMContext) -> None:
    try:
        purchase_price = parse_money(message.text)
    except Exception:
        await message.answer("Неверная сумма.")
        return

    await state.update_data(addunit_purchase_price=purchase_price)
    await state.set_state(AddUnitFlow.defects)
    await message.answer(
        "3/4 - Укажите дефекты:",
        reply_markup=unit_dash_keyboard(),
    )


@router.callback_query(F.data == "unit_defects_dash")
async def addunit_defects_dash(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    data = await state.get_data()
    defects = "-"

    await state.update_data(addunit_defects=defects)
    await state.set_state(AddUnitFlow.confirm)

    preview = (
        "4/4 - Проверьте правильность указанных данных:\n\n"
        f"Модель: {data['addunit_model_name']}\n"
        f"Категория: {data['addunit_model_category']}\n"
        f"Закупочная цена: {float(data['addunit_purchase_price']):,.0f} ₽\n"
        f"Дефекты: {defects}\n\n"
        "Напиши: yes"
    ).replace(",", " ")

    await callback.message.answer(preview)


@router.message(AddUnitFlow.defects)
async def addunit_defects(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    defects = message.text.strip() or "-"

    await state.update_data(addunit_defects=defects)

    preview = (
        "4/4 - Проверьте правильность указанных данных:\n\n"
        f"Модель: {data['addunit_model_name']}\n"
        f"Категория: {data['addunit_model_category']}\n"
        f"Закупочная цена: {float(data['addunit_purchase_price']):,.0f} ₽\n"
        f"Дефекты: {defects}\n\n"
        "Напиши: yes"
    ).replace(",", " ")

    await state.set_state(AddUnitFlow.confirm)
    await message.answer(preview)


@router.message(AddUnitFlow.confirm)
async def addunit_confirm(message: Message, state: FSMContext) -> None:
    if message.text.strip().lower() != "yes":
        await message.answer("Подтверждение не получено. Напиши yes.")
        return

    data = await state.get_data()

    with SessionLocal() as db:
        unit = create_unit(
            db=db,
            model_id=int(data["addunit_model_id"]),
            purchase_price=float(data["addunit_purchase_price"]),
            defects=data.get("addunit_defects", "-"),
        )

    await state.clear()
    await message.answer("Юнит добавлен.\n\n" + format_unit_card(unit))


@router.message(Command("findunit"))
async def cmd_findunit(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(FindUnitFlow.query)
    await message.answer("Артикул или модель юнита:")


@router.message(FindUnitFlow.query)
async def findunit_query(message: Message, state: FSMContext) -> None:
    query = message.text.strip()

    with SessionLocal() as db:
        units = search_units(db, query=query, limit=10)

    if not units:
        await message.answer("Ничего не найдено.")
        await state.clear()
        return

    if len(units) == 1:
        await message.answer(format_unit_card(units[0]))
        await state.clear()
        return

    await message.answer(format_units_list(units))
    await state.clear()
