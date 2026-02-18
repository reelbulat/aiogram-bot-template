import asyncio
import os
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from sqlalchemy import text

from db import engine, init_db
from schema import create_tables

from crm import (
    create_quote,
    get_last_quote,
    get_or_create_renter,
    add_equipment,
    find_equipment_by_alias,
    add_quote_item,
    recalc_quote_totals,
    get_quote_items,
)

# 🔒 ДОСТУП ТОЛЬКО ЭТИМ TELEGRAM ID
ALLOWED_USERS = {
    586702928,  # Булат
    384857319,  # Рифкат
}

BOT_TOKEN = os.getenv("BOT_TOKEN")

# формы (MVP)
FORM_QUOTE: dict[int, dict] = {}
FORM_EQUIP: dict[int, dict] = {}
FORM_ITEMS: dict[int, dict] = {}  # режим добавления позиций в последнюю смету


def allowed(message: types.Message) -> bool:
    return bool(message.from_user) and (message.from_user.id in ALLOWED_USERS)


def parse_date(s: str):
    return datetime.strptime(s.strip(), "%d.%m.%Y").date()


def parse_time(s: str):
    return datetime.strptime(s.strip(), "%H:%M").time()


def help_text() -> str:
    return (
        "Команды:\n"
        "/new — новая смета\n"
        "/last — последняя смета\n"
        "/items — добавить технику в последнюю смету (списком)\n"
        "/equip_new — создать позицию в каталоге\n"
        "/equip_find <слово> — найти позицию\n"
        "/db — проверка базы\n"
        "/cancel — отменить ввод\n"
    )


def fmt_quote(q: dict, items: list[dict] | None = None) -> str:
    title = q.get("project_name") or q.get("renter_display_name") or "—"

    status = (q.get("status") or "draft").lower()
    status_map = {
        "draft": "🟡 draft",
        "confirmed": "🟢 confirmed",
        "cancelled": "🔴 cancelled",
        "done": "🔵 done",
    }
    status_txt = status_map.get(status, f"🟡 {status}")

    lines = [
        f"{title} — #{q['quote_number']}",
        f"Дата: {q['load_date'].strftime('%d.%m.%Y') if hasattr(q['load_date'], 'strftime') else q['load_date']}",
        f"Время: {q['load_time'].strftime('%H:%M') if hasattr(q['load_time'], 'strftime') else q['load_time']}",
        f"Смен: {q['shifts']}",
    ]

    # Возврат показываем только если есть
    if q.get("return_time"):
        rt = q["return_time"].strftime("%H:%M") if hasattr(q["return_time"], "strftime") else str(q["return_time"])
        lines.append(f"Возврат: {rt}")

    if items is not None:
        lines.append("")
        lines.append("Позиции техники:")
        if not items:
            lines.append("— пока пусто —")
        else:
            for it in items:
                qty = it["qty"]
                unit = it["unit_price_client"]
                if it["is_subrental"]:
                    cost = it["unit_cost_subrental"]
                    lines.append(f"- {it['title']} — {qty} шт — {unit} ₽ (субаренда, себест {cost} ₽)")
                else:
                    lines.append(f"- {it['title']} — {qty} шт — {unit} ₽")

    lines += [
        "",
        f"Сумма клиента: {q.get('client_total', 0)} ₽",
        f"Субаренда: {q.get('subrental_total', 0)} ₽",
        f"Прибыль: {q.get('profit_total', 0)} ₽",
        f"Статус: {status_txt}",
    ]
    return "\n".join(lines)


def parse_items_lines(text_block: str) -> list[tuple[str, int]]:
    out = []
    for raw in text_block.splitlines():
        s0 = raw.strip()
        if not s0:
            continue

        s = s0.lower().replace("×", "x").replace("х", "x")  # русская х -> x
        qty = 1
        token = s

        # x4 / x 4 в конце
        m = re.search(r"\bx\s*(\d+)\s*$", s)
        if m:
            qty = int(m.group(1))
            token = s[: m.start()].strip()
        else:
            # 4шт / 4 шт / 4x / 4 в конце
            m2 = re.search(r"(\d+)\s*(шт|x)?\s*$", s)
            if m2:
                qty = int(m2.group(1))
                token = s[: m2.start(1)].strip()

        if not token:
            raise ValueError(f"Не понял позицию: '{s0}'")
        if qty <= 0:
            raise ValueError(f"Количество должно быть >0: '{s0}'")

        out.append((token.strip(), qty))
    return out
    import asyncio
import os
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from sqlalchemy import text

from db import engine, init_db
from schema import create_tables

from crm import (
    create_quote,
    get_last_quote,
    get_or_create_renter,
    add_equipment,
    find_equipment_by_alias,
    add_quote_item,
    recalc_quote_totals,
    get_quote_items,
)

# 🔒 ДОСТУП ТОЛЬКО ЭТИМ TELEGRAM ID
ALLOWED_USERS = {
    586702928,  # Булат
    384857319,  # Рифкат
}

BOT_TOKEN = os.getenv("BOT_TOKEN")

# формы (MVP)
FORM_QUOTE: dict[int, dict] = {}
FORM_EQUIP: dict[int, dict] = {}
FORM_ITEMS: dict[int, dict] = {}  # режим добавления позиций в последнюю смету


def allowed(message: types.Message) -> bool:
    return bool(message.from_user) and (message.from_user.id in ALLOWED_USERS)


def parse_date(s: str):
    return datetime.strptime(s.strip(), "%d.%m.%Y").date()


def parse_time(s: str):
    return datetime.strptime(s.strip(), "%H:%M").time()


def help_text() -> str:
    return (
        "Команды:\n"
        "/new — новая смета\n"
        "/last — последняя смета\n"
        "/items — добавить технику в последнюю смету (списком)\n"
        "/equip_new — создать позицию в каталоге\n"
        "/equip_find <слово> — найти позицию\n"
        "/db — проверка базы\n"
        "/cancel — отменить ввод\n"
    )


def fmt_quote(q: dict, items: list[dict] | None = None) -> str:
    title = q.get("project_name") or q.get("renter_display_name") or "—"

    status = (q.get("status") or "draft").lower()
    status_map = {
        "draft": "🟡 draft",
        "confirmed": "🟢 confirmed",
        "cancelled": "🔴 cancelled",
        "done": "🔵 done",
    }
    status_txt = status_map.get(status, f"🟡 {status}")

    lines = [
        f"{title} — #{q['quote_number']}",
        f"Дата: {q['load_date'].strftime('%d.%m.%Y') if hasattr(q['load_date'], 'strftime') else q['load_date']}",
        f"Время: {q['load_time'].strftime('%H:%M') if hasattr(q['load_time'], 'strftime') else q['load_time']}",
        f"Смен: {q['shifts']}",
    ]

    # Возврат показываем только если есть
    if q.get("return_time"):
        rt = q["return_time"].strftime("%H:%M") if hasattr(q["return_time"], "strftime") else str(q["return_time"])
        lines.append(f"Возврат: {rt}")

    if items is not None:
        lines.append("")
        lines.append("Позиции техники:")
        if not items:
            lines.append("— пока пусто —")
        else:
            for it in items:
                qty = it["qty"]
                unit = it["unit_price_client"]
                if it["is_subrental"]:
                    cost = it["unit_cost_subrental"]
                    lines.append(f"- {it['title']} — {qty} шт — {unit} ₽ (субаренда, себест {cost} ₽)")
                else:
                    lines.append(f"- {it['title']} — {qty} шт — {unit} ₽")

    lines += [
        "",
        f"Сумма клиента: {q.get('client_total', 0)} ₽",
        f"Субаренда: {q.get('subrental_total', 0)} ₽",
        f"Прибыль: {q.get('profit_total', 0)} ₽",
        f"Статус: {status_txt}",
    ]
    return "\n".join(lines)


def parse_items_lines(text_block: str) -> list[tuple[str, int]]:
    out = []
    for raw in text_block.splitlines():
        s0 = raw.strip()
        if not s0:
            continue

        s = s0.lower().replace("×", "x").replace("х", "x")  # русская х -> x
        qty = 1
        token = s

        # x4 / x 4 в конце
        m = re.search(r"\bx\s*(\d+)\s*$", s)
        if m:
            qty = int(m.group(1))
            token = s[: m.start()].strip()
        else:
            # 4шт / 4 шт / 4x / 4 в конце
            m2 = re.search(r"(\d+)\s*(шт|x)?\s*$", s)
            if m2:
                qty = int(m2.group(1))
                token = s[: m2.start(1)].strip()

        if not token:
            raise ValueError(f"Не понял позицию: '{s0}'")
        if qty <= 0:
            raise ValueError(f"Количество должно быть >0: '{s0}'")

        out.append((token.strip(), qty))
    return outimport asyncio
import os
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from sqlalchemy import text

from db import engine, init_db
from schema import create_tables

from crm import (
    create_quote,
    get_last_quote,
    get_or_create_renter,
    add_equipment,
    find_equipment_by_alias,
    add_quote_item,
    recalc_quote_totals,
    get_quote_items,
)

# 🔒 ДОСТУП ТОЛЬКО ЭТИМ TELEGRAM ID
ALLOWED_USERS = {
    586702928,  # Булат
    384857319,  # Рифкат
}

BOT_TOKEN = os.getenv("BOT_TOKEN")

# формы (MVP)
FORM_QUOTE: dict[int, dict] = {}
FORM_EQUIP: dict[int, dict] = {}
FORM_ITEMS: dict[int, dict] = {}  # режим добавления позиций в последнюю смету


def allowed(message: types.Message) -> bool:
    return bool(message.from_user) and (message.from_user.id in ALLOWED_USERS)


def parse_date(s: str):
    return datetime.strptime(s.strip(), "%d.%m.%Y").date()


def parse_time(s: str):
    return datetime.strptime(s.strip(), "%H:%M").time()


def help_text() -> str:
    return (
        "Команды:\n"
        "/new — новая смета\n"
        "/last — последняя смета\n"
        "/items — добавить технику в последнюю смету (списком)\n"
        "/equip_new — создать позицию в каталоге\n"
        "/equip_find <слово> — найти позицию\n"
        "/db — проверка базы\n"
        "/cancel — отменить ввод\n"
    )


def fmt_quote(q: dict, items: list[dict] | None = None) -> str:
    title = q.get("project_name") or q.get("renter_display_name") or "—"

    status = (q.get("status") or "draft").lower()
    status_map = {
        "draft": "🟡 draft",
        "confirmed": "🟢 confirmed",
        "cancelled": "🔴 cancelled",
        "done": "🔵 done",
    }
    status_txt = status_map.get(status, f"🟡 {status}")

    lines = [
        f"{title} — #{q['quote_number']}",
        f"Дата: {q['load_date'].strftime('%d.%m.%Y') if hasattr(q['load_date'], 'strftime') else q['load_date']}",
        f"Время: {q['load_time'].strftime('%H:%M') if hasattr(q['load_time'], 'strftime') else q['load_time']}",
        f"Смен: {q['shifts']}",
    ]

    # Возврат показываем только если есть
    if q.get("return_time"):
        rt = q["return_time"].strftime("%H:%M") if hasattr(q["return_time"], "strftime") else str(q["return_time"])
        lines.append(f"Возврат: {rt}")

    if items is not None:
        lines.append("")
        lines.append("Позиции техники:")
        if not items:
            lines.append("— пока пусто —")
        else:
            for it in items:
                qty = it["qty"]
                unit = it["unit_price_client"]
                if it["is_subrental"]:
                    cost = it["unit_cost_subrental"]
                    lines.append(f"- {it['title']} — {qty} шт — {unit} ₽ (субаренда, себест {cost} ₽)")
                else:
                    lines.append(f"- {it['title']} — {qty} шт — {unit} ₽")

    lines += [
        "",
        f"Сумма клиента: {q.get('client_total', 0)} ₽",
        f"Субаренда: {q.get('subrental_total', 0)} ₽",
        f"Прибыль: {q.get('profit_total', 0)} ₽",
        f"Статус: {status_txt}",
    ]
    return "\n".join(lines)


def parse_items_lines(text_block: str) -> list[tuple[str, int]]:
    out = []
    for raw in text_block.splitlines():
        s0 = raw.strip()
        if not s0:
            continue

        s = s0.lower().replace("×", "x").replace("х", "x")  # русская х -> x
        qty = 1
        token = s

        # x4 / x 4 в конце
        m = re.search(r"\bx\s*(\d+)\s*$", s)
        if m:
            qty = int(m.group(1))
            token = s[: m.start()].strip()
        else:
            # 4шт / 4 шт / 4x / 4 в конце
            m2 = re.search(r"(\d+)\s*(шт|x)?\s*$", s)
            if m2:
                qty = int(m2.group(1))
                token = s[: m2.start(1)].strip()

        if not token:
            raise ValueError(f"Не понял позицию: '{s0}'")
        if qty <= 0:
            raise ValueError(f"Количество должно быть >0: '{s0}'")

        out.append((token.strip(), qty))
    return out import asyncio
import os
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from sqlalchemy import text

from db import engine, init_db
from schema import create_tables

from crm import (
    create_quote,
    get_last_quote,
    get_or_create_renter,
    add_equipment,
    find_equipment_by_alias,
    add_quote_item,
    recalc_quote_totals,
    get_quote_items,
)

# 🔒 ДОСТУП ТОЛЬКО ЭТИМ TELEGRAM ID
ALLOWED_USERS = {
    586702928,  # Булат
    384857319,  # Рифкат
}

BOT_TOKEN = os.getenv("BOT_TOKEN")

# формы (MVP)
FORM_QUOTE: dict[int, dict] = {}
FORM_EQUIP: dict[int, dict] = {}
FORM_ITEMS: dict[int, dict] = {}  # режим добавления позиций в последнюю смету


def allowed(message: types.Message) -> bool:
    return bool(message.from_user) and (message.from_user.id in ALLOWED_USERS)


def parse_date(s: str):
    return datetime.strptime(s.strip(), "%d.%m.%Y").date()


def parse_time(s: str):
    return datetime.strptime(s.strip(), "%H:%M").time()


def help_text() -> str:
    return (
        "Команды:\n"
        "/new — новая смета\n"
        "/last — последняя смета\n"
        "/items — добавить технику в последнюю смету (списком)\n"
        "/equip_new — создать позицию в каталоге\n"
        "/equip_find <слово> — найти позицию\n"
        "/db — проверка базы\n"
        "/cancel — отменить ввод\n"
    )


def fmt_quote(q: dict, items: list[dict] | None = None) -> str:
    title = q.get("project_name") or q.get("renter_display_name") or "—"

    status = (q.get("status") or "draft").lower()
    status_map = {
        "draft": "🟡 draft",
        "confirmed": "🟢 confirmed",
        "cancelled": "🔴 cancelled",
        "done": "🔵 done",
    }
    status_txt = status_map.get(status, f"🟡 {status}")

    lines = [
        f"{title} — #{q['quote_number']}",
        f"Дата: {q['load_date'].strftime('%d.%m.%Y') if hasattr(q['load_date'], 'strftime') else q['load_date']}",
        f"Время: {q['load_time'].strftime('%H:%M') if hasattr(q['load_time'], 'strftime') else q['load_time']}",
        f"Смен: {q['shifts']}",
    ]

    # Возврат показываем только если есть
    if q.get("return_time"):
        rt = q["return_time"].strftime("%H:%M") if hasattr(q["return_time"], "strftime") else str(q["return_time"])
        lines.append(f"Возврат: {rt}")

    if items is not None:
        lines.append("")
        lines.append("Позиции техники:")
        if not items:
            lines.append("— пока пусто —")
        else:
            for it in items:
                qty = it["qty"]
                unit = it["unit_price_client"]
                if it["is_subrental"]:
                    cost = it["unit_cost_subrental"]
                    lines.append(f"- {it['title']} — {qty} шт — {unit} ₽ (субаренда, себест {cost} ₽)")
                else:
                    lines.append(f"- {it['title']} — {qty} шт — {unit} ₽")

    lines += [
        "",
        f"Сумма клиента: {q.get('client_total', 0)} ₽",
        f"Субаренда: {q.get('subrental_total', 0)} ₽",
        f"Прибыль: {q.get('profit_total', 0)} ₽",
        f"Статус: {status_txt}",
    ]
    return "\n".join(lines)


def parse_items_lines(text_block: str) -> list[tuple[str, int]]:
    out = []
    for raw in text_block.splitlines():
        s0 = raw.strip()
        if not s0:
            continue

        s = s0.lower().replace("×", "x").replace("х", "x")  # русская х -> x
        qty = 1
        token = s

        # x4 / x 4 в конце
        m = re.search(r"\bx\s*(\d+)\s*$", s)
        if m:
            qty = int(m.group(1))
            token = s[: m.start()].strip()
        else:
            # 4шт / 4 шт / 4x / 4 в конце
            m2 = re.search(r"(\d+)\s*(шт|x)?\s*$", s)
            if m2:
                qty = int(m2.group(1))
                token = s[: m2.start(1)].strip()

        if not token:
            raise ValueError(f"Не понял позицию: '{s0}'")
        if qty <= 0:
            raise ValueError(f"Количество должно быть >0: '{s0}'")

        out.append((token.strip(), qty))
    return out
    async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    init_db()
    create_tables()

    bot = Bot(token=BOT_TOKEN)
    dp
