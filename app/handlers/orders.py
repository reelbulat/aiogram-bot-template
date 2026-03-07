from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.db.base import SessionLocal
from app.services.client_service import get_or_create_client
from app.services.order_service import create_order, get_last_order
from app.states import NewOrderFlow
from app.utils.formatters import format_order_card
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
    await message.answer("Список техники пока пропускаем. Напиши что угодно для следующего шага.")


@router.message(NewOrderFlow.items)
async def new_order_items(message: Message, state: FSMContext) -> None:
    await state.update_data(items_raw=message.text.strip())
    await state.set_state(NewOrderFlow.client_total)
    await message.answer("Сумма клиенту:")


@router.message(NewOrderFlow.client_total)
async def new_order_client_total(message: Message, state: FSMContext) -> None:
    try:
        client_total = parse_money(message.text)
    except Exception:
        await message.answer("Неверная сумма.")
        return

    await state.update_data(client_total=client_total)
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
    await message.answer("Комментарий к заказу:")


@router.message(NewOrderFlow.comment)
async def new_order_comment(message: Message, state: FSMContext) -> None:
    await state.update_data(comment=message.text.strip())
    data = await state.get_data()

    preview = (
        f"Проверь заказ:\n\n"
        f"Проект: {data['project_name']}\n"
        f"Клиент: {data['client_name']}\n"
        f"Даты: {data['start_date']} — {data['end_date']}\n"
        f"Смен: {data['shifts']}\n"
        f"Сумма клиенту: {data['client_total']}\n"
        f"Субаренда: {data['subrental_total']}\n"
        f"Комментарий: {data['comment']}\n\n"
        f"Напиши: yes"
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
            client_total=data["client_total"],
            subrental_total=data["subrental_total"],
            comment=data["comment"],
        )

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
