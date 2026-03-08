from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import EquipmentModel, EquipmentUnit
from app.services.inventory_service import normalize_text, search_models


CATEGORY_PREFIXES = {
    "Камеры": "C",
    "Объективы": "O",
    "Свет": "L",
    "Насадки и модификаторы": "M",
    "Оперсвязь": "I",
    "Карты памяти": "S",
    "Аккумуляторы": "B",
    "Аудиосистема": "A",
}


UNIT_STATUS_LABELS = {
    "ok": "исправен",
    "repair": "ремонт",
    "archived": "архив",
}


def get_category_prefix(category: str) -> str:
    return CATEGORY_PREFIXES.get(category, "X")


def normalize_article_number(value: str) -> str:
    return value.strip().upper()


def article_exists(db: Session, article_number: str) -> bool:
    normalized = normalize_article_number(article_number)
    stmt = select(EquipmentUnit.id).where(EquipmentUnit.article_number == normalized)
    return db.execute(stmt).scalar_one_or_none() is not None


def generate_next_article(db: Session, category: str) -> str:
    prefix = get_category_prefix(category)

    stmt = select(EquipmentUnit.article_number).where(
        EquipmentUnit.article_number.like(f"{prefix}%")
    )
    rows = db.execute(stmt).scalars().all()

    max_num = 0
    for article in rows:
        if not article:
            continue
        digits = "".join(ch for ch in article if ch.isdigit())
        if digits:
            max_num = max(max_num, int(digits))

    next_num = max_num + 1
    return f"{prefix}{next_num:03d}"


def create_unit(
    db: Session,
    model_id: int,
    purchase_price: float,
    defects: str | None = None,
    article_number: str | None = None,
    status: str = "ok",
) -> EquipmentUnit:
    model = db.get(EquipmentModel, model_id)
    if not model:
        raise ValueError("Модель не найдена")

    if status not in {"ok", "repair", "archived"}:
        raise ValueError("Недопустимый статус артикла")

    article = normalize_article_number(article_number) if article_number else generate_next_article(db, model.category)

    if article_exists(db, article):
        raise ValueError("Такой артикул уже существует")

    unit = EquipmentUnit(
        model_id=model.id,
        internal_number=article,
        serial_number=None,
        article_number=article,
        purchase_price=purchase_price,
        estimated_value=float(model.estimated_value or 0),
        defects=(defects or "-").strip(),
        shifts_total=0,
        revenue_total=0,
        profit_total=0,
        status=status,
        comment=None,
    )
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return get_unit_by_id(db, unit.id)


def get_unit_by_id(db: Session, unit_id: int) -> EquipmentUnit | None:
    stmt = (
        select(EquipmentUnit)
        .options(selectinload(EquipmentUnit.model))
        .where(EquipmentUnit.id == unit_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def search_units(db: Session, query: str, limit: int = 10) -> list[EquipmentUnit]:
    q = normalize_text(query)
    if not q:
        return []

    stmt = select(EquipmentUnit).options(selectinload(EquipmentUnit.model))
    units = list(db.execute(stmt).scalars().all())

    exact_article = [
        u for u in units
        if normalize_text(u.article_number or "") == q
    ]
    if exact_article:
        return exact_article[:1]

    exact_internal = [
        u for u in units
        if normalize_text(u.internal_number or "") == q
    ]
    if exact_internal:
        return exact_internal[:1]

    article_contains = [
        u for u in units
        if q in normalize_text(u.article_number or "")
    ]
    if article_contains:
        return article_contains[:limit]

    internal_contains = [
        u for u in units
        if q in normalize_text(u.internal_number or "")
    ]
    if internal_contains:
        return internal_contains[:limit]

    model_matches = []
    for unit in units:
        model_name = unit.model.name if unit.model else ""
        if q in normalize_text(model_name):
            model_matches.append(unit)

    return model_matches[:limit]


def resolve_single_model(db: Session, query: str) -> EquipmentModel | None:
    results = search_models(db, query=query, include_inactive=False, limit=5)
    if len(results) == 1:
        return results[0]
    return None


def human_unit_status(unit: EquipmentUnit) -> str:
    return UNIT_STATUS_LABELS.get(unit.status, unit.status)
