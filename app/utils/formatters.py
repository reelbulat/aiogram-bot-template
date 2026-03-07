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


def format_order_preview_with_items(
    *,
    project_name: str,
    client_name: str,
    start_date: str,
    end_date: str,
    shifts: int,
    found_items: list[dict],
    not_found_items: list[str],
    client_total: float,
    subrental_total: float,
    comment: str,
) -> str:
    lines = [
        "Проверь заказ:",
        "",
        f"Проект: {project_name}",
        f"Клиент: {client_name}",
        f"Даты: {start_date} — {end_date}",
        f"Смен: {shifts}",
        "",
        "Позиции:",
    ]

    if found_items:
        for item in found_items:
            lines.append(
                f"• {item['name']} ×{item['qty']} = {format_money(item['line_total'])}"
            )
    else:
        lines.append("• нет найденных позиций")

    if not_found_items:
        lines.append("")
        lines.append("Не найдено:")
        for name in not_found_items:
            lines.append(f"• {name}")

    lines.extend(
        [
            "",
            f"Сумма клиенту: {format_money(client_total)}",
            f"Субаренда: {format_money(subrental_total)}",
            f"Комментарий: {comment or '-'}",
            "",
            "Напиши: yes",
        ]
    )

    return "\n".join(lines)
