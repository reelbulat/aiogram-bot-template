from app.db.models import EquipmentModel, Order


def format_money(value) -> str:
    return f"{float(value):,.0f} ₽".replace(",", " ")


def format_order_card(order: Order) -> str:
    return (
        f"Заказ #{order.order_number:05d}\n"
        f"Проект: {order.project_name}\n"
        f"Клиент ID: {order.client_id}\n"
        f"Даты: {order.start_date} — {order.end_date}\n"
        f"Смен: {order.shifts}\n"
        f"Сумма клиенту: {format_money(order.client_total)}\n"
        f"Субаренда: {format_money(order.subrental_total)}\n"
        f"Прибыль: {format_money(order.profit_total)}\n"
        f"Оплата: {order.payment_status}\n"
        f"Статус: {order.status}\n"
        f"Комментарий: {order.comment or '-'}"
    )


def format_model_card(model: EquipmentModel) -> str:
    active_text = "да" if model.is_active else "нет"

    return (
        f"Модель: {model.name}\n"
        f"Категория: {model.category}\n"
        f"Цена аренды: {format_money(model.daily_rent_price)}\n"
        f"Оценочная стоимость: {format_money(model.estimated_value)}\n"
        f"Активна: {active_text}"
    )
