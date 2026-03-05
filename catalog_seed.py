# catalog_seed.py
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from db import engine

# ⚠️ ТВОИ ДАННЫЕ: каталог + алиасы.
# Мы храним как "items": одна позиция = одно название, qty = количество на складе.
CATALOG: List[Dict[str, Any]] = [
    # CAMERAS
    {"name": "Sony FX3", "category": "camera", "day_price": 7000, "buy_price": 330000, "qty": 1,
     "aliases": ["фх3", "сонька 3", "fx3", "фикс3", "fx"]},
    {"name": "Sony ZV-E1", "category": "camera", "day_price": 4000, "buy_price": 182000, "qty": 1,
     "aliases": ["зв", "зве1", "звшка", "zve1", "zv"]},

    # LENSES FF
    {"name": "SONY FE 24–70mm F/2.8 GM II", "category": "lens_e_ff", "day_price": 3800, "buy_price": 120000, "qty": 1,
     "aliases": ["24-70", "24 70", "24-70 gm 2", "gm 2 24-70", "2470", "24-70gmii", "24-70gm2"]},
    {"name": "Vario-Tessar T* FE 16–35mm F4 ZA OSS", "category": "lens_e_ff", "day_price": 2000, "buy_price": 109000, "qty": 1,
     "aliases": ["16-35", "16 35", "16 35 f4", "16-35 f4", "1635"]},
    {"name": "Sonnar T* FE 55mm F1.8 ZA", "category": "lens_e_ff", "day_price": 1200, "buy_price": 50000, "qty": 1,
     "aliases": ["55мм", "55mm", "55 1.8", "55"]},
    {"name": "TTartisan 50mm F1.4 (Sony E, FF)", "category": "lens_e_ff", "day_price": 1200, "buy_price": None, "qty": 1,
     "aliases": ["50мм", "50mm", "50 1.4", "50"]},

    # LENSES APS-C
    {"name": "Samyang 8mm F2.8 (Sony E)", "category": "lens_e_aps", "day_price": 1000, "buy_price": 28000, "qty": 1,
     "aliases": ["фишай 8", "8мм", "8mm", "fisheye 8", "8"]},
    {"name": "TTartisan AF 35mm F1.8 (Sony E)", "category": "lens_e_aps", "day_price": 1000, "buy_price": None, "qty": 1,
     "aliases": ["35мм 1.8", "35mm 1.8", "35 1.8", "35"]},
    {"name": "7Artisans 4mm F2.8 (Sony E)", "category": "lens_e_aps", "day_price": 1000, "buy_price": None, "qty": 1,
     "aliases": ["фишай 4", "4мм", "4mm", "fisheye 4", "4"]},
    {"name": "7Artisans 35mm F1.4", "category": "lens_e_aps", "day_price": 1000, "buy_price": None, "qty": 1,
     "aliases": ["35мм 1.4", "35mm 1.4", "35 1.4"]},

    # MEDIA
    {"name": "Lexar SD Card 128GB V60", "category": "media", "day_price": 800, "buy_price": 4500, "qty": 2,
     "aliases": ["флешка на 128", "128", "128 v60", "128 в60", "128gb v60", "lexar 128"]},

    # COMMS
    {"name": "Hollyland Solidcom C1 Pro-8S", "category": "comms", "day_price": 8000, "buy_price": 247900, "qty": 1,
     "aliases": ["оперсвязь", "интеркомы", "solidcom", "c1 pro", "c1", "холлиланд"]},

    # PIPE
    {"name": "Pipe 84", "category": "light_head", "day_price": 18000, "buy_price": 610000, "qty": 1,
     "aliases": ["пайп 84", "матрас 84", "пайпик", "pipe84", "pipe 84"]},

    # APUTURE / AMARAN LIGHT HEAD
    {"name": "Aputure Storm 1200x", "category": "light_head", "day_price": 8000, "buy_price": 239900, "qty": 1,
     "aliases": ["1200", "1200х", "1200x", "1200 шторм", "storm 1200x"]},

    {"name": "Aputure LS 600c Pro", "category": "light_head", "day_price": 8000, "buy_price": 214000, "qty": 2,
     "aliases": ["600ргб", "600ц", "600c", "600 c", "600rgb"]},
    {"name": "Aputure LS 600x Pro", "category": "light_head", "day_price": 5000, "buy_price": 127900, "qty": 2,
     "aliases": ["600bi", "600x", "600х", "600икс", "600 x"]},
    {"name": "Aputure LS 600d Pro", "category": "light_head", "day_price": 4000, "buy_price": 136000, "qty": 1,
     "aliases": ["600д", "600d pro", "600dpro", "600 d pro"]},
    {"name": "Aputure LS 600d", "category": "light_head", "day_price": 4000, "buy_price": 123500, "qty": 2,
     "aliases": ["600d", "600 d", "апутюр 600д"]},

    {"name": "Aputure INFINIBAR PB12", "category": "light_head", "day_price": 2000, "buy_price": 50000, "qty": 2,
     "aliases": ["финик 12", "инфинибар 12", "пб12", "pb12", "infinibar pb12"]},

    {"name": "Aputure Accent B7c 8-Light Kit", "category": "light_head", "day_price": 3000, "buy_price": 80000, "qty": 1,
     "aliases": ["балбы", "лампочка", "b7c kit", "b7c 8", "б7ц кит"]},
    {"name": "Aputure Accent B7c", "category": "light_head", "day_price": 400, "buy_price": None, "qty": 1,
     "aliases": ["b7c", "б7ц", "b7", "лампочка b7c"]},

    {"name": "Amaran 300c", "category": "light_head", "day_price": 2000, "buy_price": 38000, "qty": 4,
     "aliases": ["300c", "300ц", "300ргб", "амаран 300с", "амаран 300c", "amaran 300c"]},

    {"name": "Amaran F22c", "category": "light_head", "day_price": 2500, "buy_price": 58900, "qty": 2,
     "aliases": ["коврик 22с", "коврик ргб", "ковер ргб", "ковер ц", "f22c", "22c"]},
    {"name": "Amaran F22x", "category": "light_head", "day_price": 2000, "buy_price": 46000, "qty": 2,
     "aliases": ["коврик 22х", "ковер 22х", "ковер биколор", "ковер би", "f22x", "22x"]},

    {"name": "Amaran PT4c", "category": "light_head", "day_price": 1500, "buy_price": 25500, "qty": 2,
     "aliases": ["пт4ц", "pt4c", "pt 4c"]},

    # MODIFIERS / ACCESSORIES
    {"name": "Aputure Spotlight 26", "category": "modifier", "day_price": 1500, "buy_price": 26000, "qty": 1,
     "aliases": ["спот 26", "spot 26", "spotlight 26"]},

    {"name": "Lightdome 150", "category": "modifier", "day_price": 1000, "buy_price": 21000, "qty": 2,
     "aliases": ["дом 150", "лайтдом 150", "lightdome150", "ld150"]},
    {"name": "Lightdome 90", "category": "modifier", "day_price": 750, "buy_price": 19000, "qty": 1,
     "aliases": ["дом 90", "лайтдом 90", "lightdome90", "ld90"]},

    {"name": "Lantern 90", "category": "modifier", "day_price": 750, "buy_price": 12900, "qty": 2,
     "aliases": ["шарик большой", "шарик 90", "лартерн 90", "лантерн большой", "lantern 90"]},
    {"name": "Lantern 26", "category": "modifier", "day_price": 500, "buy_price": 7490, "qty": 3,
     "aliases": ["шарик мал", "лантерн 26", "шарик 26", "lantern 26"]},

    {"name": "Френель F10", "category": "modifier", "day_price": 750, "buy_price": 19490, "qty": 2,
     "aliases": ["ф10", "f10", "фринель ф10", "фринель 10", "фринель на 600", "фринель большая", "большая фринель"]},
    {"name": "Френель 2X", "category": "modifier", "day_price": 500, "buy_price": 9800, "qty": 2,
     "aliases": ["х2", "2х", "фринель х2", "фринель 2х", "фринель мал", "2x", "x2"]},

    # OTHER
    {"name": "Profoto B1X", "category": "flash", "day_price": 4000, "buy_price": 130000, "qty": 1,
     "aliases": ["b1x", "б1х", "profoto b1x"]},

    {"name": "KingMa 300W V-Mount", "category": "power", "day_price": 600, "buy_price": 16500, "qty": 6,
     "aliases": ["300вх", "вимаунт 300", "v-mount 300wh", "v-mount 300", "kingma 300"]},
    {"name": "Зарядная станция KingMa для V-Mount", "category": "power", "day_price": 500, "buy_price": 15500, "qty": 1,
     "aliases": ["зарядка для вимаунтов", "зарядка v-mount", "зарядка kingma"]},

    {"name": "Hollyland Lark M2 Combo", "category": "audio", "day_price": 600, "buy_price": 14919, "qty": 1,
     "aliases": ["петли", "петлички", "lark m2", "hollyland lark"]},
]


def _norm(s: str) -> str:
    s = s.strip().lower()
    s = s.replace("ё", "е")
    s = re.sub(r"\s+", " ", s)
    return s


def _aliases_with_name(name: str, aliases: List[str]) -> List[str]:
    base = [_norm(a) for a in aliases if a and a.strip()]
    base.append(_norm(name))
    # уникализация
    out = []
    seen = set()
    for a in base:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def _detect_table_and_columns(conn) -> Tuple[str, List[str]]:
    # Пытаемся найти таблицу каталога (equipment / items / inventory)
    candidates = ["equipment", "equipments", "items", "inventory", "catalog"]
    for t in candidates:
        res = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public' AND table_name=:t
            LIMIT 1
        """), {"t": t}).fetchone()
        if res:
            table = res[0]
            cols = [r[0] for r in conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=:t
                ORDER BY ordinal_position
            """), {"t": table}).fetchall()]
            return table, cols
    raise RuntimeError("Не нашёл таблицу каталога (equipment/items/inventory/catalog) в public schema.")


def seed_catalog() -> Dict[str, Any]:
    """
    Идемпотентный сид: добавляет позиции, если их ещё нет.
    Сопоставляет колонки динамически (чтобы не зависеть от точного schema.py).
    """
    added = 0
    skipped = 0

    with engine.begin() as conn:
        table, cols = _detect_table_and_columns(conn)

        # маппинг колонок (под разные варианты)
        col_name = "name" if "name" in cols else ("title" if "title" in cols else None)
        col_category = "category" if "category" in cols else None
        col_day_price = "day_price" if "day_price" in cols else ("price" if "price" in cols else ("rent_price" if "rent_price" in cols else None))
        col_buy_price = "buy_price" if "buy_price" in cols else ("purchase_price" if "purchase_price" in cols else None)
        col_qty = "qty" if "qty" in cols else ("quantity" if "quantity" in cols else None)
        col_aliases = "aliases" if "aliases" in cols else ("alias" if "alias" in cols else None)
        col_status = "status" if "status" in cols else None

        if not col_name:
            raise RuntimeError(f"В таблице {table} нет колонки name/title — не могу сидить каталог.")

        for it in CATALOG:
            name = it["name"].strip()
            aliases = _aliases_with_name(name, it.get("aliases", []))

            # проверка "уже есть" по name
            exists = conn.execute(
                text(f"SELECT 1 FROM {table} WHERE {col_name}=:name LIMIT 1"),
                {"name": name}
            ).fetchone()

            if exists:
                skipped += 1
                continue

            payload: Dict[str, Any] = {col_name: name}

            if col_category and it.get("category") is not None:
                payload[col_category] = it["category"]

            if col_day_price and it.get("day_price") is not None:
                payload[col_day_price] = int(it["day_price"])

            if col_buy_price:
                payload[col_buy_price] = int(it["buy_price"]) if it.get("buy_price") else None

            if col_qty:
                payload[col_qty] = int(it.get("qty", 1))

            if col_aliases:
                # если колонка текстовая — кладём строкой; если json/jsonb — Postgres сам кастанёт через to_jsonb ниже
                payload[col_aliases] = ",".join(aliases)

            if col_status:
                payload[col_status] = "ok"  # по умолчанию не "ремонт"

            cols_sql = ", ".join(payload.keys())
            vals_sql = ", ".join([f":{k}" for k in payload.keys()])

            conn.execute(text(f"INSERT INTO {table} ({cols_sql}) VALUES ({vals_sql})"), payload)
            added += 1

    return {"added": added, "skipped": skipped}
