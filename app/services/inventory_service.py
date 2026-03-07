import re
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EquipmentModel


def normalize_text(value: str) -> str:
    text = value.lower().strip()
    text = text.replace("ё", "е")
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("х", "x")
    text = re.sub(r"[^a-zа-я0-9]+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def sync_search_names(db: Session) -> None:
    models = db.execute(select(EquipmentModel)).scalars().all()
    changed = False

    for model in models:
        normalized = normalize_text(model.name)
        if model.search_name != normalized:
            model.search_name = normalized
            changed = True

        if model.is_active is None:
            model.is_active = True
            changed = True

    if changed:
        db.commit()


def create_equipment_model(
    db: Session,
    name: str,
    category: str,
    daily_rent_price: float = 0,
    estimated_value: float = 0,
    aliases: list[str] | None = None,
    comment: str | None = None,
) -> EquipmentModel:
    search_name = normalize_text(name)

    existing = db.execute(
        select(EquipmentModel).where(EquipmentModel.search_name == search_name)
    ).scalar_one_or_none()

    if existing:
        raise ValueError("Такая модель уже существует.")

    model = EquipmentModel(
        name=name.strip(),
        category=category.strip(),
        search_name=search_name,
        is_active=True,
        daily_rent_price=daily_rent_price,
        estimated_value=estimated_value,
        aliases=aliases or [],
        comment=comment,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def get_model_by_id(db: Session, model_id: int) -> EquipmentModel | None:
    return db.get(EquipmentModel, model_id)


def search_models(
    db: Session,
    query: str,
    include_inactive: bool = True,
    limit: int = 5,
) -> list[EquipmentModel]:
    q = normalize_text(query)
    if not q:
        return []

    stmt = select(EquipmentModel)

    if not include_inactive:
        stmt = stmt.where(EquipmentModel.is_active.is_(True))

    all_models = list(db.execute(stmt).scalars().all())

    exact = [m for m in all_models if m.search_name == q]
    if exact:
        return exact[:1]

    contains = [m for m in all_models if q in m.search_name]
    if contains:
        return contains[:limit]

    ranked = sorted(
        all_models,
        key=lambda m: SequenceMatcher(None, q, m.search_name).ratio(),
        reverse=True,
    )

    result = []
    for model in ranked:
        ratio = SequenceMatcher(None, q, model.search_name).ratio()
        if ratio >= 0.45:
            result.append(model)
        if len(result) >= limit:
            break

    return result


def update_equipment_model(
    db: Session,
    model_id: int,
    *,
    name: str | None = None,
    category: str | None = None,
    daily_rent_price: float | None = None,
    estimated_value: float | None = None,
) -> EquipmentModel | None:
    model = db.get(EquipmentModel, model_id)
    if not model:
        return None

    if name is not None:
        new_search_name = normalize_text(name)

        existing = db.execute(
            select(EquipmentModel).where(
                EquipmentModel.search_name == new_search_name,
                EquipmentModel.id != model_id,
            )
        ).scalar_one_or_none()

        if existing:
            raise ValueError("Модель с таким названием уже существует.")

        model.name = name.strip()
        model.search_name = new_search_name

    if category is not None:
        model.category = category.strip()

    if daily_rent_price is not None:
        model.daily_rent_price = daily_rent_price

    if estimated_value is not None:
        model.estimated_value = estimated_value

    db.commit()
    db.refresh(model)
    return model
