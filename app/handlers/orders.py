from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.db.base import SessionLocal
from app.services.client_service import get_or_create_client
from app.services.inventory_service import search_models
from app.services.order_service import (
    add_order_item,
    create_order,
    get_last_order,
    get_order_by_number,
    recalc_order_totals,
    update_order_status,
)
from app.services.parser_service import parse_items_block
from app.states import NewOrderFlow
from app.utils.formatters import format_order_card, format_order_preview_with_items
from app.utils.validators import (
    calc_shifts,
    parse_datetime_flexible,
    parse_money,
    parse_percent,
)

router = Router()


def quote_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="quote_confirm")],
            [InlineKeyboardButton(text="🗂️ Изм. название проекта", callback_data="quote_edit_project")],
            [InlineKeyboardButton(text="👤 Изм. клиента", callback_data="quote_edit_client")],
            [InlineKeyboardButton(text="🗓️ Изм. дату и время", callback_data="quote_edit_dates")],
            [InlineKeyboardButton(text="☑️ Изм. позиции техники", callback_data="quote_edit_items")],
            [InlineKeyboardButton(text="🏷️ Изм. скидку", callback_data="quote_edit_discount")],
            [InlineKeyboardButton(text="💭 Изм. коментарий", callback_data="quote_edit_comment")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="quote_cancel")],
        ]
    )


def discount_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="10", callback_data="discount_10"),
                InlineKeyboardButton(text="20", callback_data="discount_20"),
                InlineKeyboardButton(text="30", callback_data="discount_30"),
            ],
            [
                InlineKeyboardButton(text="40", callback_data="discount_40"),
                InlineKeyboardButton(text="50", callback_data="discount_50"),
                InlineKeyboardButton(text="60", callback_data="discount_60"),
            ],
        ]
    )


def zero_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="0", callback_data="subrental_0")]
        ]
    )


def dash_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="-", callback_data="comment_dash")]
        ]
    )


def order_status_keyboard(order_id: int, status: str) -> InlineKeyboardMarkup | None:
    if status == "draft":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🟢 Подтвердить смету", callback_data=f"order_confirm_{order_id}")],
                [InlineKeyboardButton(text="🔴 Отменить смету", callback_data=f"order_cancel_{order_id}")],
            ]
        )

    if status == "confirmed":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔵 Завершить заказ", callback_data=f"order_done_{order_id}")],
                [InlineKeyboardButton(text="🔴 Отменить смету", callback_data=f"order_cancel_{order_id}")],
            ]
        )

    return None


def extract_order_number(text: str) -> int | None:
    raw = text.strip()
    parts = raw.split(maxsplit=1)

    if len(parts) < 2:
        return None

    value = parts[1].strip()
    digits = "".join(ch for ch in value if ch.isdigit())

    if not digits:
        return None

    return int(digits)


async def remove_markup(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


async def send_preview(message: Message, state: FSMContext) -> None:
    data = await state.get_data()

    start_at = datetime.fromisoformat(data["start_at_iso"])
    end_at = datetime.fromisoformat(data["end_at_iso"])

    preview = format_order_preview_with_items(
        project_name=data["project_name"],
        client_name=data["client_name"],
        start_at=start_at,
        end_at=end_at,
        shifts=int(data["shifts"]),
        found_items=data.get("found_items", []),
        not_found_items=data.get("not_found_items", []),
        subtotal=float(data.get("subtotal", 0)),
        discount_percent=float(data.get("discount_percent", 0)),
        client_total=float(data.get("client_total", 0)),
        subrental_total=float(data.get("subrental_total", 0)),
        comment=data.get("comment", ""),
    )

    await state.set_state(NewOrderFlow.confirm)
    await message.answer(preview, reply_markup=quote_preview_keyboard())


async def send_saved_order(message: Message, order) -> None:
    await message.answer(
        format_order_card(order),
        reply_markup=order_status_keyboard(order.id, order.status),
    )


async def finalize_quote(message: Message, state: FSMContext) -> None:
    data = await state.get_data()

    start_at = datetime.fromisoformat(data["start_at_iso"])
    end_at = datetime.fromisoformat(data["end_at_iso"])

    with SessionLocal() as db:
        client = get_or_create_client(db, data["client_name"])

        order = create_order(
            db=db,
            project_name=data["project_name"],
            client_id=client.id,
            start_at=start_at,
            end_at=end_at,
            shifts=int(data["shifts"]),
            discount_percent=float(data.get("discount_percent", 0)),
            subrental_total=float(data.get("subrental_total", 0)),
            comment=data.get("comment", ""),
        )

        for item in data.get("found_items", []):
            add_order_item(
                db=db,
                order_id=order.id,
                model_id=item["model_id"],
                qty=item["qty"],
                unit_price_client=item["unit_price_client"],
                is_subrental=False,
                subrental_cost=0,
            )

        recalc_order_totals(db, order.id)
        order = get_order_by_number(db, order.order_number)

    await state.clear()
    await send_saved_order(message, order)


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(NewOrderFlow.project_name)
    await message.answer("1/9 - Название проекта:")


@router.message(NewOrderFlow.project_name)
async def new_order_project_name(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_target = data.get("edit_target")

    await state.update_data(project_name=message.text.strip())

    if edit_target == "project_name":
        await state.update_data(edit_target="")
        await send_preview(message, state)
        return

    await state.set_state(NewOrderFlow.client_name)
    await message.answer("2/9 - Клиент / Заказчик")


@router.message(NewOrderFlow.client_name)
async def new_order_client_name(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_target = data.get("edit_target")

    await state.update_data(client_name=message.text.strip())

    if edit_target == "client_name":
        await state.update_data(edit_target="")
        await send_preview(message, state)
        return

    await state.set_state(NewOrderFlow.start_at)
    await message.answer("3/9 - Дата и время начала смены:")


@router.message(NewOrderFlow.start_at)
async def new_order_start_at(message: Message, state: FSMContext) -> None:
    try:
        start_at = parse_datetime_flexible(message.text)
    except Exception as e:
        await message.answer(str(e))
        return

    await state.update_data(start_at_iso=start_at.isoformat())
    await state.set_state(NewOrderFlow.end_at)
    await message.answer("4/9 - Дата и время окончания смены:")


@router.message(NewOrderFlow.end_at)
async def new_order_end_at(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_target = data.get("edit_target")

    try:
        start_at = datetime.fromisoformat(data["start_at_iso"])
        end_at = parse_datetime_flexible(message.text)
        shifts = calc_shifts(start_at, end_at)
    except Exception as e:
        await message.answer(str(e))
        return

    await state.update_data(
        end_at_iso=end_at.isoformat(),
        shifts=shifts,
    )

    if edit_target == "dates":
        raw_items = data.get("raw_items", "").strip()
        found_items: list[dict] = []
        not_found_items: list[str] = []
        subtotal = 0.0

        if raw_items:
            parsed_items = parse_items_block(raw_items)

            with SessionLocal() as db:
                for raw_name, qty in parsed_items:
                    results = search_models(
                        db,
                        query=raw_name,
                        include_inactive=False,
                        limit=5,
                    )

                    if not results:
                        not_found_items.append(raw_name)
                        continue

                    model = results[0]
                    base_unit_price = float(model.daily_rent_price)
                    unit_price_client = base_unit_price * shifts
                    line_total = unit_price_client * qty
                    subtotal += line_total

                    found_items.append(
                        {
                            "model_id": model.id,
                            "name": model.name,
                            "qty": qty,
                            "base_unit_price": base_unit_price,
                            "unit_price_client": unit_price_client,
                            "line_total": line_total,
                        }
                    )

        discount_percent = float(data.get("discount_percent", 0))
        client_total = subtotal - (subtotal * discount_percent / 100)

        await state.update_data(
            found_items=found_items,
            not_found_items=not_found_items,
            subtotal=subtotal,
            client_total=client_total,
            edit_target="",
        )
        await send_preview(message, state)
        return

    await state.set_state(NewOrderFlow.items)
    await message.answer(
        f"5/9 - Количество смен: {shifts}\n"
        "Напишите список техники и ее количество:"
    )


@router.message(NewOrderFlow.items)
async def new_order_items(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_target = data.get("edit_target")
    raw_items = message.text.strip()

    try:
        parsed_items = parse_items_block(raw_items)
    except Exception as e:
        await message.answer(f"Ошибка в списке техники: {e}")
        return

    shifts = int(data["shifts"])
    found_items: list[dict] = []
    not_found_items: list[str] = []
    subtotal = 0.0

    with SessionLocal() as db:
        for raw_name, qty in parsed_items:
            results = search_models(db, query=raw_name, include_inactive=False, limit=5)

            if not results:
                not_found_items.append(raw_name)
                continue

            model = results[0]
            base_unit_price = float(model.daily_rent_price)
            unit_price_client = base_unit_price * shifts
            line_total = unit_price_client * qty
            subtotal += line_total

            found_items.append(
                {
                    "model_id": model.id,
                    "name": model.name,
                    "qty": qty,
                    "base_unit_price": base_unit_price,
                    "unit_price_client": unit_price_client,
                    "line_total": line_total,
                }
            )

    discount_percent = float(data.get("discount_percent", 0))
    client_total = subtotal - (subtotal * discount_percent / 100)

    await state.update_data(
        raw_items=raw_items,
        found_items=found_items,
        not_found_items=not_found_items,
        subtotal=subtotal,
        client_total=client_total,
    )

    if edit_target == "items":
        await state.update_data(edit_target="")
        await send_preview(message, state)
        return

    await state.set_state(NewOrderFlow.discount_percent)
    await message.answer(
        "6/9 - Укажите скидку для клиента:",
        reply_markup=discount_keyboard(),
    )


@router.message(NewOrderFlow.discount_percent)
async def new_order_discount_percent(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_target = data.get("edit_target")

    try:
        discount_percent = parse_percent(message.text)
    except Exception:
        await message.answer("Неверный процент.")
        return

    subtotal = float(data.get("subtotal", 0))
    client_total = subtotal - (subtotal * discount_percent / 100)

    await state.update_data(
        discount_percent=discount_percent,
        client_total=client_total,
    )

    if edit_target == "discount_percent":
        await state.update_data(edit_target="")
        await send_preview(message, state)
        return

    await state.set_state(NewOrderFlow.subrental_total)
    await message.answer(
        "7/9 - Субаренда:",
        reply_markup=zero_keyboard(),
    )


@router.message(NewOrderFlow.subrental_total)
async def new_order_subrental_total(message: Message, state: FSMContext) -> None:
    try:
        subrental_total = parse_money(message.text)
    except Exception:
        await message.answer("Неверная сумма.")
        return

    await state.update_data(subrental_total=subrental_total)
    await state.set_state(NewOrderFlow.comment)
    await message.answer(
        "8/9 - Укажите комментарий для заказа:",
        reply_markup=dash_keyboard(),
    )


@router.message(NewOrderFlow.comment)
async def new_order_comment(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_target = data.get("edit_target")

    await state.update_data(comment=message.text.strip())

    if edit_target == "comment":
        await state.update_data(edit_target="")
        await send_preview(message, state)
        return

    await send_preview(message, state)


@router.message(NewOrderFlow.confirm)
async def new_order_confirm_message(message: Message, state: FSMContext) -> None:
    if message.text.strip().lower() == "yes":
        await finalize_quote(message, state)
        return

    await message.answer("Используй кнопки под сметой.")


@router.callback_query(F.data.startswith("discount_"))
async def quick_discount(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    value = callback.data.split("_")[1]

    data = await state.get_data()
    edit_target = data.get("edit_target")

    discount_percent = float(value)
    subtotal = float(data.get("subtotal", 0))
    client_total = subtotal - (subtotal * discount_percent / 100)

    await state.update_data(
        discount_percent=discount_percent,
        client_total=client_total,
    )

    if edit_target == "discount_percent":
        await state.update_data(edit_target="")
        await remove_markup(callback)
        await send_preview(callback.message, state)
        return

    await remove_markup(callback)
    await state.set_state(NewOrderFlow.subrental_total)
    await callback.message.answer(
        "7/9 - Субаренда:",
        reply_markup=zero_keyboard(),
    )


@router.callback_query(F.data == "subrental_0")
async def quick_subrental_zero(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await remove_markup(callback)
    await state.update_data(subrental_total=0)
    await state.set_state(NewOrderFlow.comment)
    await callback.message.answer(
        "8/9 - Укажите комментарий для заказа:",
        reply_markup=dash_keyboard(),
    )


@router.callback_query(F.data == "comment_dash")
async def quick_comment_dash(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await remove_markup(callback)

    data = await state.get_data()
    edit_target = data.get("edit_target")

    await state.update_data(comment="-")

    if edit_target == "comment":
        await state.update_data(edit_target="")
        await send_preview(callback.message, state)
        return

    await send_preview(callback.message, state)


@router.callback_query(F.data == "quote_confirm")
async def quote_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await remove_markup(callback)
    await finalize_quote(callback.message, state)


@router.callback_query(F.data == "quote_edit_project")
async def quote_edit_project(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await remove_markup(callback)
    await state.update_data(edit_target="project_name")
    await state.set_state(NewOrderFlow.project_name)
    await callback.message.answer("1/9 - Название проекта:")


@router.callback_query(F.data == "quote_edit_client")
async def quote_edit_client(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await remove_markup(callback)
    await state.update_data(edit_target="client_name")
    await state.set_state(NewOrderFlow.client_name)
    await callback.message.answer("2/9 - Клиент / Заказчик")


@router.callback_query(F.data == "quote_edit_dates")
async def quote_edit_dates(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await remove_markup(callback)
    await state.update_data(edit_target="dates")
    await state.set_state(NewOrderFlow.start_at)
    await callback.message.answer("3/9 - Дата и время начала смены:")


@router.callback_query(F.data == "quote_edit_items")
async def quote_edit_items(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await remove_markup(callback)

    data = await state.get_data()
    shifts = int(data.get("shifts", 1))

    await state.update_data(edit_target="items")
    await state.set_state(NewOrderFlow.items)
    await callback.message.answer(
        f"5/9 - Количество смен: {shifts}\n"
        "Напишите список техники и ее количество:"
    )


@router.callback_query(F.data == "quote_edit_discount")
async def quote_edit_discount(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await remove_markup(callback)
    await state.update_data(edit_target="discount_percent")
    await state.set_state(NewOrderFlow.discount_percent)
    await callback.message.answer(
        "6/9 - Укажите скидку для клиента:",
        reply_markup=discount_keyboard(),
    )


@router.callback_query(F.data == "quote_edit_comment")
async def quote_edit_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await remove_markup(callback)
    await state.update_data(edit_target="comment")
    await state.set_state(NewOrderFlow.comment)
    await callback.message.answer(
        "8/9 - Укажите комментарий для заказа:",
        reply_markup=dash_keyboard(),
    )


@router.callback_query(F.data == "quote_cancel")
async def quote_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await remove_markup(callback)
    await state.clear()
    await callback.message.answer("Создание сметы отменено.")


@router.message(Command("order"))
async def cmd_order(message: Message) -> None:
    order_number = extract_order_number(message.text or "")

    if order_number is None:
        await message.answer("Используй: /order 1")
        return

    with SessionLocal() as db:
        order = get_order_by_number(db, order_number)

    if not order:
        await message.answer("Смета не найдена.")
        return

    await send_saved_order(message, order)


@router.callback_query(F.data.startswith("order_confirm_"))
async def order_confirm(callback: CallbackQuery) -> None:
    await callback.answer()
    order_id = int(callback.data.split("_")[-1])

    with SessionLocal() as db:
        order = update_order_status(db, order_id, "confirmed")

    if not order:
        await callback.message.answer("Смета не найдена.")
        return

    await callback.message.edit_text(
        format_order_card(order),
        reply_markup=order_status_keyboard(order.id, order.status),
    )


@router.callback_query(F.data.startswith("order_done_"))
async def order_done(callback: CallbackQuery) -> None:
    await callback.answer()
    order_id = int(callback.data.split("_")[-1])

    with SessionLocal() as db:
        order = update_order_status(db, order_id, "done")

    if not order:
        await callback.message.answer("Смета не найдена.")
        return

    await callback.message.edit_text(
        format_order_card(order),
        reply_markup=order_status_keyboard(order.id, order.status),
    )


@router.callback_query(F.data.startswith("order_cancel_"))
async def order_cancel(callback: CallbackQuery) -> None:
    await callback.answer()
    order_id = int(callback.data.split("_")[-1])

    with SessionLocal() as db:
        order = update_order_status(db, order_id, "cancelled")

    if not order:
        await callback.message.answer("Смета не найдена.")
        return

    await callback.message.edit_text(
        format_order_card(order),
        reply_markup=order_status_keyboard(order.id, order.status),
    )


@router.message(Command("last"))
async def cmd_last(message: Message) -> None:
    with SessionLocal() as db:
        order = get_last_order(db)

    if not order:
        await message.answer("Смет пока нет.")
        return

    await send_saved_order(message, order)
