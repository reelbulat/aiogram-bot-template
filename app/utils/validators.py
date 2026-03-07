from datetime import datetime


def parse_date(value: str):
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def parse_int(value: str) -> int:
    return int(value.strip())


def parse_money(value: str) -> float:
    clean = (
        value.strip()
        .replace("₽", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    return float(clean)
