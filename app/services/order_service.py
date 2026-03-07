from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Order, OrderItem


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


def get_order_by_number(db: Session, order_number: int) -> Order | None:
    stmt = select(Order).where(Order.order_number == order_number)
    return db.execute(stmt).scalar_one_or_none()


def add_order_item(
    db: Session,
    order_id: int,
    model_id: int,
    qty: int,
    unit_price_client: float,
    is_subrental: bool = False,
    subrental_cost: float = 0,
    comment: str | None = None,
) -> OrderItem:
    item = OrderItem(
        order_id=order_id,
        model_id=model_id,
        qty=qty,
        unit_price_client=unit_price_client,
        is_subrental=is_subrental,
        subrental_cost=subrental_cost,
        comment=comment,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_order_items(db: Session, order_id: int) -> list[OrderItem]:
    stmt = select(OrderItem).where(OrderItem.order_id == order_id)
    return list(db.execute(stmt).scalars().all())


def recalc_order_totals(db: Session, order_id: int) -> None:
    order = db.get(Order, order_id)
    if not order:
        return

    items = get_order_items(db, order_id)

    items_total = sum(float(item.unit_price_client) * item.qty for item in items)
    subrental_total = sum(float(item.subrental_cost) for item in items)

    order.client_total = items_total
    order.subrental_total = subrental_total
    order.profit_total = items_total - subrental_total
    order.debt_total = items_total - float(order.paid_total)

    db.commit()
    db.refresh(order)


def get_order_items_with_models(db: Session, order_id: int) -> list[OrderItem]:
    stmt = select(OrderItem).where(OrderItem.order_id == order_id)
    return list(db.execute(stmt).scalars().all())
