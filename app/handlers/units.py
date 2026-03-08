from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db.base import SessionLocal
from app.services.unit_service import (
    article_exists,
    create_unit,
    generate_next_article,
    resolve_single_model,
    search_units,
)
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


def addarticle_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="addarticle_confirm")],
            [InlineKeyboardButton(text="🆔 Изменить артикул", callback_data="addarticle_edit_article")],
            [InlineKeyboardButton(text="🔧 Изменить статус", callback_data="addarticle_edit_status")],
            [InlineKeyboardButton(text="💰 Изменить закуп. стоимость", callback_data="addarticle_edit_purchase")],
        ]
    )


def article_status_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="исправен", callback_data="article_status_ok")],
            [InlineKeyboardButton(text="ремонт", callback_data="article_status_repair")],
            [InlineKeyboardButton(text="архив", callback_data="article_status_archived")],
        ]
    )


def human_status(status: str) -> str:
    return {
        "ok": "исправен",
        "repair": "ремонт",
        "archived": "архив",
    }.get(status, status)


async def clear_markup(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


async def send_addarticle_preview(message: Message, state: FSMContext) -> None:
    data = await state.get_data()

    preview = (
        "4/4 - Проверьте правильность указанных данных:\n\n"
        f"Артикул: {data['addunit_article_number']}\n"
        f"Модель: {data['addunit_model_name']}\n"
        f"Категория: {data['addunit_model_category']}\n"
        f"Тех. статус: {human_status(data.get('addunit_status', 'ok'))}\n"
        f"Закуп. стоимость: {float(data['addunit_purchase_price']):,.0f} ₽\n"
        f"Дефекты: {data.get('addunit_defects', '-')}"
    ).replace(",", " ")

    await state.set_state(AddUnitFlow.confirm)
    await message.answer(preview, reply_markup=addarticle_preview_keyboard())


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
        if model:
            article_number = generate_next_article(db, model.category)
        else:
            article_number = None

    if not model:
        await message.answer("Не смог однозначно определить модель. Напиши точнее.")
        return

    await state.update_data(
        addunit_model_id=model.id,
        addunit_model_name=model.name,
        addunit_model_category=model.category,
        addunit_article_number=article_number,
        addunit_status="ok",
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

    data = await state.get_data()
    edit_target = data.get("addunit_edit_target")

    await state.update_data(addunit_purchase_price=purchase_price)

    if edit_target == "purchase_price":
        await state.update_data(addunit_edit_target="")
        await send_addarticle_preview(message, state)
        return

    await state.set_state(AddUnitFlow.defects)
    await message.answer(
        "3/4 - Укажите дефекты:",
        reply_markup=unit_dash_keyboard(),
    )


@router.callback_query(F.data == "unit_defects_dash")
async def addunit_defects_dash(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_markup(callback)

    await state.update_data(addunit_defects="-")
    await send_addarticle_preview(callback.message, state)


@router.message(AddUnitFlow.defects)
async def addunit_defects(message: Message, state: FSMContext) -> None:
    defects = message.text.strip() or "-"
    await state.update_data(addunit_defects=defects)
    await send_addarticle_preview(message, state)


@router.callback_query(F.data == "addarticle_edit_article")
async def addarticle_edit_article(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_markup(callback)
    await state.set_state(AddUnitFlow.article_number)
    await callback.message.answer("Новый артикул:")


@router.message(AddUnitFlow.article_number)
async def addunit_article_number(message: Message, state: FSMContext) -> None:
    article_number = message.text.strip().upper()
    if not article_number:
        await message.answer("Артикул не может быть пустым.")
        return

    with SessionLocal() as db:
        exists = article_exists(db, article_number)

    if exists:
        await message.answer("Такой артикул уже существует.")
        return

    await state.update_data(addunit_article_number=article_number)
    await send_addarticle_preview(message, state)


@router.callback_query(F.data == "addarticle_edit_status")
async def addarticle_edit_status(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_markup(callback)
    await callback.message.answer(
        "Выберите тех. статус:",
        reply_markup=article_status_keyboard(),
    )


@router.callback_query(F.data == "article_status_ok")
async def article_status_ok(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_markup(callback)
    await state.update_data(addunit_status="ok")
    await send_addarticle_preview(callback.message, state)


@router.callback_query(F.data == "article_status_repair")
async def article_status_repair(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_markup(callback)
    await state.update_data(addunit_status="repair")
    await send_addarticle_preview(callback.message, state)


@router.callback_query(F.data == "article_status_archived")
async def article_status_archived(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_markup(callback)
    await state.update_data(addunit_status="archived")
    await send_addarticle_preview(callback.message, state)


@router.callback_query(F.data == "addarticle_edit_purchase")
async def addarticle_edit_purchase(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_markup(callback)
    await state.update_data(addunit_edit_target="purchase_price")
    await state.set_state(AddUnitFlow.purchase_price)
    await callback.message.answer("Новая закуп. стоимость:")


@router.callback_query(F.data == "addarticle_confirm")
async def addarticle_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_markup(callback)

    data = await state.get_data()

    with SessionLocal() as db:
        try:
            unit = create_unit(
                db=db,
                model_id=int(data["addunit_model_id"]),
                purchase_price=float(data["addunit_purchase_price"]),
                defects=data.get("addunit_defects", "-"),
                article_number=data.get("addunit_article_number"),
                status=data.get("addunit_status", "ok"),
            )
        except ValueError as e:
            await callback.message.answer(str(e))
            return

    await state.clear()
    await callback.message.answer("Артикул добавлен.\n\n" + format_unit_card(unit))


@router.message(AddUnitFlow.confirm)
async def addunit_confirm_text(message: Message) -> None:
    await message.answer("Используй кнопки под карточкой.")


@router.message(Command("findunit"))
async def cmd_findunit(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(FindUnitFlow.query)
    await message.answer("Артикул или модель:")


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
