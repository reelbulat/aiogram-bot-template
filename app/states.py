from aiogram.fsm.state import State, StatesGroup


class NewOrderFlow(StatesGroup):
    project_name = State()
    client_name = State()
    start_date = State()
    end_date = State()
    shifts = State()
    items = State()
    client_total = State()
    subrental_total = State()
    comment = State()
    confirm = State()
