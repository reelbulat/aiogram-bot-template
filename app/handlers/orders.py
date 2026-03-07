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
    recalc_order_totals,
)
from app.services.parser_service import parse_items_block
from app.states import NewOrderFlow
from app.utils.formatters import format_order_card, format_order_preview_with_items
from app.utils.validators import parse_date, parse_int, parse_money

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
    await state.set_state(NewOrderFlow.start_date)
    await message.answer("Дата начала аренды в формате YYYY-MM-DD:")


@router.message(NewOrderFlow.start_date)
async def new_order_start_date(message: Message, state: FSMContext) -> None:
    try:
        start_date = parse_date(message.text)
    except Exception:
        await message.answer("Неверная дата. Формат: YYYY-MM-DD")
        return

    await state.update_data(start_date=str(start_date))
    await state.set_state(NewOrderFlow.end_date)
    await message.answer("Дата конца аренды в формате YYYY-MM-DD:")


@router.message(NewOrderFlow.end_date)
async def new_order_end_date(message: Message, state: FSMContext) -> None:
    try:
        end_date = parse_date(message.text)
    except Exception:
        await message.answer("Неверная дата. Формат: YYYY-MM-DD")
        return

    await state.update_data(end_date=str(end_date))
    await state.set_state(NewOrderFlow.shifts)
    await message.answer("Количество смен:")


@router.message(NewOrderFlow.shifts)
async def new_order_shifts(message: Message, state: FSMContext) -> None:
    try:
        shifts = parse_int(message.text)
        if shifts <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введите целое число больше 0.")
        return

    await state.update_data(shifts=shifts)
    await state.set_state(NewOrderFlow.items)
    await message.answer(
        "Введи технику списком, каждая позиция с новой строки.\n"
        "Примеры:\n"
        "Sony FX3\n"
        "Amaran F22x x2\n"
        "Lantern 90 2шт"
    )


@router.message(NewOrderFlow.items)
async def new_order_items(message: Message, state: FSMContext) -> None:
    raw_items = message.text.strip()

    try:
        parsed_items = parse_items_block(raw_items)
    except Exception as e:
        await message.answer(f"Ошибка в списке техники: {e}")
        return

    found_items: list[dict] = []
    not_found_items: list[str] = []
    client_total = 0.0

    with SessionLocal() as db:
        for raw_name, qty in parsed_items:
            results = search_models(db, query=raw_name, include_inactive=False, limit=5)

            if not results:
                not_found_items.append(raw_name)
                continue

            model = results[0]
            line_total = float(model.daily_rent_price) * qty
            client_total += line_total

            found_items.append(
                {
                    "model_id": model.id,
                    "name": model.name,
                    "qty": qty,
                    "unit_price_client": float(model.daily_rent_price),
                    "line_total": line_total,
                }
            )

    await state.update_data(
        raw_items=raw_items,
        found_items=found_items,
        not_found_items=not_found_items,
        client_total=client_total,
    )

    await state.set_state(NewOrderFlow.subrental_total)
    await message.answer(
        "Техника обработана.\n"
        f"Найдено позиций: {len(found_items)}\n"
        f"Не найдено: {len(not_found_items)}\n\n"
        "Теперь введи сумму субаренды:"
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
    await message.answer("Комментарий к заказу:")


@router.message(NewOrderFlow.comment)
async def new_order_comment(message: Message, state: FSMContext) -> None:
    await state.update_data(comment=message.text.strip())
    data = await state.get_data()

    preview = format_order_preview_with_items(
        project_name=data["project_name"],
        client_name=data["client_name"],
        start_date=data["start_date"],
        end_date=data["end_date"],
        shifts=data["shifts"],
        found_items=data.get("found_items", []),
        not_found_items=data.get("not_found_items", []),
        client_total=data.get("client_total", 0),
        subrental_total=data.get("subrental_total", 0),
        comment=data["comment"],
    )

    await state.set_state(NewOrderFlow.confirm)
    await message.answer(preview)


@router.message(NewOrderFlow.confirm)
async def new_order_confirm(message: Message, state: FSMContext) -> None:
    if message.text.strip().lower() != "yes":
        await message.answer("Подтверждение не получено. Напиши yes.")
        return

    data = await state.get_data()

    with SessionLocal() as db:
        client = get_or_create_client(db, data["client_name"])

        order = create_order(
            db=db,
            project_name=data["project_name"],
            client_id=client.id,
            start_date=parse_date(data["start_date"]),
            end_date=parse_date(data["end_date"]),
            shifts=int(data["shifts"]),
            client_total=0,
            subrental_total=data["subrental_total"],
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

        order = get_last_order(db)

    await state.clear()
    await message.answer("Заказ создан.\n\n" + format_order_card(order))


@router.message(Command("last"))
async def cmd_last(message: Message) -> None:
    with SessionLocal() as db:
        order = get_last_order(db)

    if not order:
        await message.answer("Заказов пока нет.")
        return

    await message.answer(format_order_card(order))
