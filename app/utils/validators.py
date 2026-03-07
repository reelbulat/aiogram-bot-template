import math
import re
from datetime import date, datetime, time


MONTHS = {
    "янв": 1,
    "январ": 1,
    "фев": 2,
    "феврал": 2,
    "мар": 3,
    "март": 3,
    "апр": 4,
    "апрел": 4,
    "мая": 5,
    "май": 5,
    "июн": 6,
    "июнъ": 6,
    "июл": 7,
    "июлъ": 7,
    "авг": 8,
    "август": 8,
    "сен": 9,
    "сентябр": 9,
    "окт": 10,
    "октябр": 10,
    "ноя": 11,
    "ноябр": 11,
    "дек": 12,
    "декабр": 12,
}


def parse_int(value: str) -> int:
    return int(value.strip())


def parse_money(value: str) -> float:
    clean = (
        value.strip()
        .replace("₽", "")
        .replace("р", "")
        .replace("руб", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    return float(clean)


def parse_percent(value: str) -> float:
    clean = value.strip().replace("%", "").replace(",", ".")
    result = float(clean)
    if result < 0:
        raise ValueError("Скидка не может быть меньше 0")
    return result


def parse_date_flexible(value: str, default_year: int | None = None) -> date:
    raw = value.strip().lower().replace("ё", "е")
    default_year = default_year or datetime.now().year

    m = re.match(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})$", raw)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3))
        if year < 100:
            year += 2000
        return date(year, month, day)

    m = re.match(r"^(\d{1,2})[.\-/](\d{1,2})$", raw)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        return date(default_year, month, day)

    m = re.match(r"^(\d{1,2})\s+([а-я]+)(?:\s+(\d{2,4}))?$", raw)
    if m:
        day = int(m.group(1))
        month_raw = m.group(2)
        year_raw = m.group(3)

        month = None
        for key, value in MONTHS.items():
            if month_raw.startswith(key):
                month = value
                break

        if month is None:
            raise ValueError("Не понял месяц")

        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000
        else:
            year = default_year

        return date(year, month, day)

    raise ValueError("Не понял дату")


def parse_time_flexible(value: str) -> time:
    raw = value.strip().lower().replace("ё", "е")
    raw = re.sub(r"\s+", " ", raw)

    m = re.match(r"^(\d{1,2})[:.\s](\d{2})$", raw)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        return time(hour, minute)

    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(утра|дня|вечера|ночи)$", raw)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        period = m.group(3)

        if period == "утра":
            if hour == 12:
                hour = 0

        elif period == "дня":
            if 1 <= hour <= 11:
                hour += 12
            elif hour == 12:
                hour = 12

        elif period == "вечера":
            if 1 <= hour <= 11:
                hour += 12
            elif hour == 12:
                hour = 12

        elif period == "ночи":
            if hour == 12:
                hour = 0

        return time(hour, minute)

    raise ValueError("Не понял время")


def parse_datetime_flexible(value: str) -> datetime:
    raw = value.strip()

    patterns = [
        r"^(.+?)\s+(\d{1,2}[:.\s]\d{2})$",
        r"^(.+?)\s+(\d{1,2}(?::\d{2})?\s*(?:утра|дня|вечера|ночи))$",
    ]

    for pattern in patterns:
        m = re.match(pattern, raw, flags=re.IGNORECASE)
        if m:
            date_part = m.group(1).strip()
            time_part = m.group(2).strip()
            d = parse_date_flexible(date_part)
            t = parse_time_flexible(time_part)
            return datetime.combine(d, t)

    raise ValueError("Формат: 09.03.2026 07:00 или 9 марта 7 утра")


def calc_shifts(start_at: datetime, end_at: datetime) -> int:
    if end_at <= start_at:
        raise ValueError("Окончание должно быть позже начала")

    duration_seconds = (end_at - start_at).total_seconds()
    return max(1, math.ceil(duration_seconds / 86400))


def format_datetime_ru(value: datetime | None) -> str:
    if not value:
        return "-"
    return value.strftime("%d.%m.%Y %H:%M")
