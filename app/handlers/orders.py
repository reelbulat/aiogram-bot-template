from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.db.base import SessionLocal
from app.services.client_service import get_or_create_client
from app.services.inventory_service import search_models
from app.services.order_service import (
    add_order_item,
    create_order,
    get_last_order,
    get_order_by_number,
    recalc_order_totals,
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


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(NewOrderFlow.project_name)
    await message.answer("Название проекта:")


@router.message(NewOrderFlow.project_name)
async def new_order_project_name(message: Message, state: FSMContext) -> None:
    await state.update_data(project_name=message.text.strip())
    await state.set_state(NewOrderFlow.client_name)
    await message.answer("Клиент / компания:")


@router.message(NewOrderFlow.client_name)
async def new_order_client_name(message: Message, state: FSMContext) -> None:
    await state.update_data(client_name=message.text.strip())
    await state.set_state(NewOrderFlow.start_at)
    await message.answer(
        "Дата и время начала.\n"
        "Примеры:\n"
        "09.03.2026 07:00\n"
        "09.03.26 21 00\n"
        "9 марта 7 утра"
    )


@router.message(NewOrderFlow.start_at)
async def new_order_start_at(message: Message, state: FSMContext) -> None:
    try:
        start_at = parse_datetime_flexible(message.text)
    except Exception as e:
        await message.answer(str(e))
        return

    await state.update_data(start_at_iso=start_at.isoformat())
    await state.set_state(NewOrderFlow.end_at)
    await message.answer(
        "Дата и время окончания.\n"
        "Примеры:\n"
        "10.03.2026 07:00\n"
        "9 марта 16:00\n"
        "9 марта 9 вечера\n"
        "10.03.2026 21:00"
    )


@router.message(NewOrderFlow.end_at)
async def new_order_end_at(message: Message, state: FSMContext) -> None:
    data = await state.get_data()

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
    await state.set_state(NewOrderFlow.items)
    await message.answer(
        f"Смен посчитано автоматически: {shifts}\n\n"
        "Введи технику списком, каждая позиция с новой строки.\n"
        "Примеры:\n"
        "Sony FX3\n"
        "Amaran F22x x2\n"
        "Lantern 90 2шт"
    )


@router.message(NewOrderFlow.items)
async def new_order_items(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
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
            unit_price_client = float(model.daily_rent_price) * shifts
            line_total = unit_price_client * qty
            subtotal += line_total

            found_items.append(
                {
                    "model_id": model.id,
                    "name": model.name,
                    "qty": qty,
                    "unit_price_client": unit_price_client,
                    "line_total": line_total,
                }
            )

    await state.update_data(
        raw_items=raw_items,
        found_items=found_items,
        not_found_items=not_found_items,
        subtotal=subtotal,
    )

    await state.set_state(NewOrderFlow.discount_percent)
    await message.answer("Скидка в процентах. Если нет скидки — отправь 0")


@router.message(NewOrderFlow.discount_percent)
async def new_order_discount_percent(message: Message, state: FSMContext) -> None:
    data = await state.get_data()

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

    await state.set_state(NewOrderFlow.subrental_total)
    await message.answer("Субаренда:")


@router.message(NewOrderFlow.subrental_total)
async def new_order_subrental_total(message: Message, state: FSMContext) -> None:
    try:
        subrental_total = parse_money(message.text)
    except Exception:
        await message.answer("Неверная сумма.")
        return

    await state.update_data(subrental_total=subrental_total)
    await state.set_state(NewOrderFlow.comment)
    await message.answer("Комментарий к смете:")


@router.message(NewOrderFlow.comment)
async def new_order_comment(message: Message, state: FSMContext) -> None:
    data = await state.get_data()

    start_at = datetime.fromisoformat(data["start_at_iso"])
    end_at = datetime.fromisoformat(data["end_at_iso"])

    await state.update_data(comment=message.text.strip())

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
        comment=message.text.strip(),
    )

    await state.set_state(NewOrderFlow.confirm)
    await message.answer(preview)


@router.message(NewOrderFlow.confirm)
async def new_order_confirm(message: Message, state: FSMContext) -> None:
    if message.text.strip().lower() != "yes":
        await message.answer("Подтверждение не получено. Напиши yes.")
        return

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
            comment=data["comment"],
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
    await message.answer("Смета создана.\n\n" + format_order_card(order))


@router.message(Command("last"))
async def cmd_last(message: Message) -> None:
    with SessionLocal() as db:
        order = get_last_order(db)

    if not order:
        await message.answer("Смет пока нет.")
        return

    await message.answer(format_order_card(order))
