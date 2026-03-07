from aiogram.fsm.state import State, StatesGroup


class NewOrderFlow(StatesGroup):
    project_name = State()
    client_name = State()
    start_at = State()
    end_at = State()
    items = State()
    discount_percent = State()
    subrental_total = State()
    comment = State()
    confirm = State()


class AddModelFlow(StatesGroup):
    name = State()
    category = State()
    daily_rent_price = State()
    estimated_value = State()
    confirm = State()


class FindModelFlow(StatesGroup):
    query = State()


class EditModelFlow(StatesGroup):
    query = State()
    field = State()
    value = State()
