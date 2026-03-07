from app.db.models import EquipmentModel, Order
from app.utils.validators import format_datetime_ru


def format_money(value) -> str:
    return f"{float(value):,.0f} ₽".replace(",", " ")


def format_order_card(order: Order) -> str:
    client_name = order.client.name if getattr(order, "client", None) else f"ID {order.client_id}"

    lines = [
        f"Смета #{order.order_number:05d}",
        "",
        f"Проект: {order.project_name}",
        f"Клиент: {client_name}",
        f"Начало: {format_datetime_ru(order.start_at)}",
        f"Окончание: {format_datetime_ru(order.end_at)}",
        f"Смен: {order.shifts}",
        "",
        "Позиции:",
    ]

    if getattr(order, "items", None):
        for item in order.items:
            model_name = item.model.name if getattr(item, "model", None) else f"model_id={item.model_id}"
            line_total = float(item.unit_price_client) * item.qty
            lines.append(f"{item.qty}х | {model_name} = {format_money(line_total)}")
    else:
        lines.append("-")

    lines.extend(
        [
            "",
            f"Скидка: {float(order.discount_percent or 0):.0f}%",
            f"Итого: {format_money(order.client_total)}",
            f"Субаренда: {format_money(order.subrental_total)}",
            "",
            f"Комментарий: {order.comment or '-'}",
        ]
    )

    return "\n".join(lines)


def format_model_card(model: EquipmentModel) -> str:
    active_text = "да" if model.is_active else "нет"

    return (
        f"Модель: {model.name}\n"
        f"Категория: {model.category}\n"
        f"Цена аренды: {format_money(model.daily_rent_price)}\n"
        f"Оценочная стоимость: {format_money(model.estimated_value)}\n"
        f"Активна: {active_text}"
    )


def format_order_preview_with_items(
    *,
    project_name: str,
    client_name: str,
    start_at,
    end_at,
    shifts: int,
    found_items: list[dict],
    not_found_items: list[str],
    subtotal: float,
    discount_percent: float,
    client_total: float,
    subrental_total: float,
    comment: str,
) -> str:
    lines = [
        "Проверь смету:",
        "",
        f"Проект: {project_name}",
        f"Клиент: {client_name}",
        f"Начало: {format_datetime_ru(start_at)}",
        f"Окончание: {format_datetime_ru(end_at)}",
        f"Смен: {shifts}",
        "",
        "Позиции:",
    ]

    if found_items:
        for item in found_items:
            lines.append(f"{item['qty']}х | {item['name']} = {format_money(item['line_total'])}")
    else:
        lines.append("-")

    if not_found_items:
        lines.extend(["", "Не найдено:"])
        for name in not_found_items:
            lines.append(f"• {name}")

    lines.extend(
        [
            "",
            f"Скидка: {discount_percent:.0f}%",
            f"Итого: {format_money(client_total)}",
            f"Субаренда: {format_money(subrental_total)}",
            "",
            f"Комментарий: {comment or '-'}",
            "",
            "Напиши: yes",
        ]
    )

    return "\n".join(lines)
