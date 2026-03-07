from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Client


def get_client_by_name(db: Session, name: str) -> Client | None:
    stmt = select(Client).where(Client.name.ilike(name.strip()))
    return db.execute(stmt).scalar_one_or_none()


def create_client(
    db: Session,
    name: str,
    client_type: str = "person",
    phone: str | None = None,
    telegram: str | None = None,
    email: str | None = None,
    comment: str | None = None,
) -> Client:
    client = Client(
        type=client_type,
        name=name.strip(),
        phone=phone,
        telegram=telegram,
        email=email,
        comment=comment,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def get_or_create_client(db: Session, name: str) -> Client:
    existing = get_client_by_name(db, name)
    if existing:
        return existing
    return create_client(db=db, name=name)
