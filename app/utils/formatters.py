from datetime import datetime
from html import escape

from app.db.models import EquipmentModel, EquipmentUnit, Order


MONTHS_RU_GEN = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def format_money(value) -> str:
    return f"{float(value):,.0f} ₽".replace(",", " ")


def format_money_compact(value) -> str:
    return f"{float(value):,.0f}₽".replace(",", " ")


def format_booking_dates_and_times(
    start_at: datetime | None,
    end_at: datetime | None,
) -> tuple[str, str]:
    if not start_at or not end_at:
        return "-", "-"

    if start_at.year == end_at.year:
        if start_at.month == end_at.month:
            if start_at.day == end_at.day:
                dates_text = f"{start_at.day} {MONTHS_RU_GEN[start_at.month]} {start_at.year}"
            else:
                dates_text = f"{start_at.day}–{end_at.day} {MONTHS_RU_GEN[start_at.month]} {start_at.year}"
        else:
            dates_text = (
                f"{start_at.day} {MONTHS_RU_GEN[start_at.month]} — "
                f"{end_at.day} {MONTHS_RU_GEN[end_at.month]} {start_at.year}"
            )
    else:
        dates_text = (
            f"{start_at.day} {MONTHS_RU_GEN[start_at.month]} {start_at.year} — "
            f"{end_at.day} {MONTHS_RU_GEN[end_at.month]} {end_at.year}"
        )

    times_text = f"{start_at.strftime('%H:%M')}–{end_at.strftime('%H:%M')}"
    return dates_text, times_text


def format_status_label(status: str) -> str:
    mapping = {
        "draft": "🟡 черновик",
        "confirmed": "🟢 подтверждена",
        "done": "🔵 завершена",
        "cancelled": "🔴 отменена",
    }
    return mapping.get(status, status)


def format_order_card(order: Order) -> str:
    client_name = (
        order.client.name
        if getattr(order, "client", None)
        else f"ID {order.client_id}"
    )
    dates_text, times_text = format_booking_dates_and_times(order.start_at, order.end_at)

    lines = [
        f"Смета #{order.order_number:05d}",
        "",
        f"Проект: {escape(order.project_name)}",
        f"Клиент: {escape(client_name)}",
        f"Даты: {dates_text}",
        f"Время: {times_text}",
        f"Смен: {order.shifts}",
        f"Статус: {format_status_label(order.status)}",
        "",
        "Позиции:",
    ]

    if getattr(order, "items", None):
        for item in order.items:
            model_name = (
                item.model.name
                if getattr(item, "model", None)
                else f"model_id={item.model_id}"
            )

            if getattr(item, "model", None):
                base_price = float(item.model.daily_rent_price)
            else:
                base_price = float(item.unit_price_client) / max(int(order.shifts or 1), 1)

            line_total = float(item.unit_price_client) * item.qty

            lines.append(
                f"{item.qty}х | {escape(model_name)} = "
                f"{format_money_compact(base_price)} * {order.shifts} = {format_money(line_total)}"
            )
    else:
        lines.append("-")

    lines.extend(
        [
            "",
            f"Итого без скидки: {format_money(order.subtotal or 0)}",
            f"Скидка: {float(order.discount_percent or 0):.0f}%",
            f"Субаренда: {format_money(order.subrental_total)}",
            "",
            f"<b>Итого: {format_money(order.client_total)}</b>",
            "",
            f"Комментарий: {escape(order.comment or '-')}",
        ]
    )

    return "\n".join(lines)


def format_model_card(model: EquipmentModel) -> str:
    active_text = "да" if model.is_active else "нет"

    return (
        f"Модель: {escape(model.name)}\n"
        f"Категория: {escape(model.category)}\n"
        f"Цена аренды: {format_money(model.daily_rent_price)}\n"
        f"Оценочная стоимость: {format_money(model.estimated_value)}\n"
        f"Активна: {active_text}"
    )


def format_unit_card(unit: EquipmentUnit) -> str:
    model_name = unit.model.name if getattr(unit, "model", None) else f"model_id={unit.model_id}"

    purchase_price = float(unit.purchase_price or 0)
    profit_total = float(unit.profit_total or 0)
    revenue_total = float(unit.revenue_total or 0)

    if purchase_price > 0:
        payback_percent = (profit_total / purchase_price) * 100
        payback_remaining = max(0, purchase_price - profit_total)
        payback_text = f"{payback_percent:.1f}% | осталось {format_money(payback_remaining)}"
    else:
        payback_text = "-"

    status_map = {
        "ok": "исправен",
        "repair": "ремонт",
        "archived": "архив",
    }

    return (
        f"Юнит: {escape(unit.article_number or '-')}\n"
        f"Модель: {escape(model_name)}\n"
        f"Тех. статус: {status_map.get(unit.status, unit.status)}\n"
        f"Дефекты: {escape(unit.defects or '-')}\n"
        f"Закупка: {format_money(unit.purchase_price)}\n"
        f"Оценка: {format_money(unit.estimated_value)}\n"
        f"Смен: {int(unit.shifts_total or 0)}\n"
        f"Выручка: {format_money(revenue_total)}\n"
        f"Прибыль: {format_money(profit_total)}\n"
        f"Окупаемость: {payback_text}"
    )


def format_units_list(units: list[EquipmentUnit]) -> str:
    if not units:
        return "Ничего не найдено."

    blocks = []
    for unit in units:
        model_name = unit.model.name if getattr(unit, "model", None) else f"model_id={unit.model_id}"
        status_map = {
            "ok": "исправен",
            "repair": "ремонт",
            "archived": "архив",
        }
        blocks.append(
            f"{escape(unit.article_number or '-')}"
            f" | {escape(model_name)}"
            f" | {status_map.get(unit.status, unit.status)}"
        )
    return "\n".join(blocks)


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
    dates_text, times_text = format_booking_dates_and_times(start_at, end_at)

    lines = [
        "9/9 - Проверь смету....",
        "",
        f"Проект: {escape(project_name)}",
        f"Клиент: {escape(client_name)}",
        f"Даты: {dates_text}",
        f"Время: {times_text}",
        f"Смен: {shifts}",
        "",
        "Позиции:",
    ]

    if found_items:
        for item in found_items:
            lines.append(
                f"{item['qty']}х | {escape(item['name'])} = "
                f"{format_money_compact(item['base_unit_price'])} * {shifts} = {format_money(item['line_total'])}"
            )
    else:
        lines.append("-")

    if not_found_items:
        lines.extend(["", "Не найдено:"])
        for name in not_found_items:
            lines.append(f"• {escape(name)}")

    lines.extend(
        [
            "",
            f"Итого без скидки: {format_money(subtotal)}",
            f"Скидка: {discount_percent:.0f}%",
            f"Субаренда: {format_money(subrental_total)}",
            "",
            f"<b>Итого: {format_money(client_total)}</b>",
            "",
            f"Комментарий: {escape(comment or '-')}",
        ]
    )

    return "\n".join(lines)
