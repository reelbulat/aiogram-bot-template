import re


def parse_item_line(line: str) -> tuple[str, int]:
    raw = line.strip()
    if not raw:
        raise ValueError("Пустая строка")

    qty = 1

    patterns = [
        r"^(.*)\s+x(\d+)$",
        r"^(.*)\s+х(\d+)$",
        r"^(.*)\s+(\d+)шт$",
        r"^(.*)\s+(\d+)\s*шт$",
        r"^(.*)\s+\*(\d+)$",
    ]

    for pattern in patterns:
        match = re.match(pattern, raw, flags=re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            qty = int(match.group(2))
            if qty <= 0:
                raise ValueError("Количество должно быть больше 0")
            return name, qty

    return raw, 1


def parse_items_block(text: str) -> list[tuple[str, int]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result: list[tuple[str, int]] = []

    for line in lines:
        result.append(parse_item_line(line))

    return result
