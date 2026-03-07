from sqlalchemy import text
from db import engine

DEFAULT_STATUS = "active"

def norm_aliases(s: str) -> str:
    parts = []
    for a in (s or "").replace("(", ",").replace(")", ",").split(","):
        a = a.strip().lower()
        if a:
            parts.append(a)

    seen = set()
    out = []
    for a in parts:
        if a not in seen:
            out.append(a)
            seen.add(a)
    return ", ".join(out)

ITEMS = [
    dict(name="Sony FX3", category="camera", daily_price=7000, purchase_price=330000, qty_total=1, aliases="фх3, сонька 3, fx3, фикс3, fx"),
    dict(name="Sony ZV-E1", category="camera", daily_price=4000, purchase_price=182000, qty_total=1, aliases="зв, зве1, звшка, zve1, zv"),

    dict(name="SONY FE 24–70mm F2.8 GM II", category="lens_ff", daily_price=3800, purchase_price=120000, qty_total=1, aliases="24-70, 24-70 gm 2, gm 2 24-70, 24 70, 24-70gm2, 24 70 gm2"),
    dict(name="Vario-Tessar T* FE 16–35mm F4 ZA OSS", category="lens_ff", daily_price=2000, purchase_price=109000, qty_total=1, aliases="16-35, 16 35 f4, 16 35 ф4, 16-35 f4"),
    dict(name="Sonnar T* FE 55mm F1.8 ZA", category="lens_ff", daily_price=1200, purchase_price=50000, qty_total=1, aliases="55мм, 55mm, 55"),
    dict(name="TTartisan 50mm F1.4 Sony E FF", category="lens_ff", daily_price=1200, purchase_price=None, qty_total=1, aliases="50мм, 50mm, 50"),

    dict(name="Samyang 8mm F2.8 Sony E", category="lens_crop", daily_price=1000, purchase_price=28000, qty_total=1, aliases="фишай 8, fisheye 8, 8мм, 8mm, samyang 8"),
    dict(name="TTartisan AF 35mm F1.8 Sony E", category="lens_crop", daily_price=1000, purchase_price=None, qty_total=1, aliases="35мм 1.8, 35mm 1.8, 35 1.8, ttartisan 35 1.8"),
    dict(name="7Artisans 4mm F2.8 Sony E", category="lens_crop", daily_price=1000, purchase_price=None, qty_total=1, aliases="фишай 4, fisheye 4, 4мм, 4mm, 7artisans 4"),
    dict(name="7Artisans 35mm F1.4", category="lens_crop", daily_price=1000, purchase_price=None, qty_total=1, aliases="35мм 1.4, 35mm 1.4, 35 1.4, 7artisans 35 1.4"),

    dict(name="Lexar SD Card 128GB V60", category="media", daily_price=800, purchase_price=4500, qty_total=2, aliases="флешка на 128, 128 v60, 128gb v60, 128, lexar 128 v60"),

    dict(name="Hollyland Solidcom C1 Pro-8S", category="comms", daily_price=8000, purchase_price=247900, qty_total=1, aliases="оперсвязь, интеркомы, интерком, solidcom, c1 pro"),
    dict(name="Hollyland Lark M2 Combo", category="audio", daily_price=600, purchase_price=14919, qty_total=1, aliases="петли, петлички, lark m2, hollyland lark"),

    dict(name="Pipe 84", category="light_special", daily_price=18000, purchase_price=610000, qty_total=1, aliases="пайп 84, матрас 84, пайпик, pipe84"),

    dict(name="Aputure Storm 1200x", category="light", daily_price=8000, purchase_price=239900, qty_total=1, aliases="1200, 1200х, 1200x, 1200 шторм, storm 1200x"),
    dict(name="Aputure LS 600c Pro", category="light", daily_price=8000, purchase_price=214000, qty_total=2, aliases="600ргб, 600rgb, 600ц, 600c, 600c pro"),
    dict(name="Aputure LS 600x Pro", category="light", daily_price=5000, purchase_price=127900, qty_total=2, aliases="600bi, 600x, 600х, 600икс, 600x pro"),
    dict(name="Aputure LS 600d Pro", category="light", daily_price=4000, purchase_price=136000, qty_total=1, aliases="600д про, 600d pro, 600dpro"),
    dict(name="Aputure LS 600d", category="light", daily_price=4000, purchase_price=123500, qty_total=2, aliases="600д, 600d"),
    dict(name="Aputure INFINIBAR PB12", category="light", daily_price=2000, purchase_price=50000, qty_total=2, aliases="финик 12, инфинибар 12, пб12, infini, infinibar pb12, pb12"),

    dict(name="Aputure Accent B7c 8-Light Kit", category="practical", daily_price=3000, purchase_price=80000, qty_total=1, aliases="балбы, лампочка, b7c кит, b7c kit, б7ц кит"),
    dict(name="Aputure Accent B7c", category="practical", daily_price=400, purchase_price=None, qty_total=1, aliases="b7c, б7ц, лампочка b7c"),

    dict(name="Amaran 300c", category="light", daily_price=2000, purchase_price=38000, qty_total=4, aliases="300c, 300ц, 300ргб, амаран 300с, амаран 300c, amaran300c"),
    dict(name="Amaran F22c", category="light", daily_price=2500, purchase_price=58900, qty_total=2, aliases="коврик 22с, коврик ргб, ковер ргб, ковер ц, f22c"),
    dict(name="Amaran F22x", category="light", daily_price=2000, purchase_price=46000, qty_total=2, aliases="коврик 22х, ковер 22х, ковер биколор, ковер би, f22x"),
    dict(name="Amaran PT4c", category="light", daily_price=1500, purchase_price=25500, qty_total=2, aliases="пт4ц, pt4c"),

    dict(name="Aputure Spotlight 26", category="modifier", daily_price=1500, purchase_price=26000, qty_total=1, aliases="спот 26, spotlight 26"),
    dict(name="Lightdome 150", category="modifier", daily_price=1000, purchase_price=21000, qty_total=2, aliases="дом 150, лайтдом 150, lightdome150"),
    dict(name="Lightdome 90", category="modifier", daily_price=750, purchase_price=19000, qty_total=1, aliases="дом 90, лайтдом 90, lightdome90"),
    dict(name="Lantern 90", category="modifier", daily_price=750, purchase_price=12900, qty_total=2, aliases="шарик большой, шарик 90, лартерн 90, лантерн 90, lantern 90"),
    dict(name="Lantern 26", category="modifier", daily_price=500, purchase_price=7490, qty_total=3, aliases="шарик мал, лантерн 26, шарик 26, lantern 26"),
    dict(name="Френель F10", category="modifier", daily_price=750, purchase_price=19490, qty_total=2, aliases="ф10, f10, фринель ф10, фринель 10, фринель на 600, фринель большая, большая фринель"),
    dict(name="Френель 2X", category="modifier", daily_price=500, purchase_price=9800, qty_total=2, aliases="х2, 2х, 2x, x2, фринель 2х, фринель x2, фринель мал"),

    dict(name="Profoto B1X", category="flash", daily_price=4000, purchase_price=130000, qty_total=1, aliases="b1x, б1х, profoto b1x"),
    dict(name="KingMa 300W V-Mount", category="power", daily_price=600, purchase_price=16500, qty_total=6, aliases="300вх, 300wh, вимаунт 300, v-mount 300wh, v-mount 300, kingma 300"),
    dict(name="Зарядная станция KingMa для V-Mount", category="power", daily_price=500, purchase_price=15500, qty_total=1, aliases="зарядка для вимаунтов, зарядка v-mount, kingma charger"),
]

SQL_SELECT_BY_NAME = text("SELECT id, aliases FROM equipment WHERE name = :name LIMIT 1")

SQL_INSERT = text("""
INSERT INTO equipment (name, category, daily_price, purchase_price, qty_total, status, aliases)
VALUES (:name, :category, :daily_price, :purchase_price, :qty_total, :status, :aliases)
""")

SQL_UPDATE = text("""
UPDATE equipment
SET category=:category,
    daily_price=:daily_price,
    purchase_price=:purchase_price,
    qty_total=:qty_total,
    status=:status,
    aliases=:aliases
WHERE id=:id
""")

def merge_aliases(old: str, new: str) -> str:
    old_n = norm_aliases(old or "")
    new_n = norm_aliases(new or "")
    if not old_n:
        return new_n
    if not new_n:
        return old_n
    return norm_aliases(old_n + ", " + new_n)

def seed():
    inserted = 0
    updated = 0

    with engine.begin() as conn:
        for it in ITEMS:
            it = dict(it)
            it["aliases"] = norm_aliases(it.get("aliases", ""))
            it["status"] = it.get("status") or DEFAULT_STATUS

            row = conn.execute(SQL_SELECT_BY_NAME, {"name": it["name"]}).fetchone()
            if row:
                eq_id = int(row[0])
                old_aliases = row[1] or ""
                it["aliases"] = merge_aliases(old_aliases, it["aliases"])
                conn.execute(SQL_UPDATE, {**it, "id": eq_id})
                updated += 1
            else:
                conn.execute(SQL_INSERT, it)
                inserted += 1

    print(f"equipment seeded. inserted={inserted}, updated={updated}, total={len(ITEMS)}")

if __name__ == "__main__":
    seed()
