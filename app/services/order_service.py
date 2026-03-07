from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Order


def get_next_order_number(db: Session) -> int:
    stmt = select(func.max(Order.order_number))
    last_number = db.execute(stmt).scalar_one_or_none()
    return 1 if last_number is None else last_number + 1


def create_order(
    db: Session,
    project_name: str,
    client_id: int,
    start_date: date,
    end_date: date,
    shifts: int,
    client_total: Decimal | float = 0,
    subrental_total: Decimal | float = 0,
    comment: str | None = None,
) -> Order:
    client_total = Decimal(str(client_total))
    subrental_total = Decimal(str(subrental_total))
    profit_total = client_total - subrental_total
    debt_total = client_total

    order = Order(
        order_number=get_next_order_number(db),
        project_name=project_name.strip(),
        client_id=client_id,
        start_date=start_date,
        end_date=end_date,
        shifts=shifts,
        status="draft",
        comment=comment,
        client_total=client_total,
        subrental_total=subrental_total,
        expenses_total=Decimal("0"),
        profit_total=profit_total,
        payment_status="unpaid",
        paid_total=Decimal("0"),
        debt_total=debt_total,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def get_last_order(db: Session) -> Order | None:
    stmt = select(Order).order_by(Order.id.desc()).limit(1)
    return db.execute(stmt).scalar_one_or_none()
