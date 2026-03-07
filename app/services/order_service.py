from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Order, OrderItem


def get_next_order_number(db: Session) -> int:
    stmt = select(func.max(Order.order_number))
    last_number = db.execute(stmt).scalar_one_or_none()
    return 1 if last_number is None else last_number + 1


def create_order(
    db: Session,
    project_name: str,
    client_id: int,
    start_at: datetime,
    end_at: datetime,
    shifts: int,
    discount_percent: Decimal | float = 0,
    subrental_total: Decimal | float = 0,
    comment: str | None = None,
) -> Order:
    discount_percent = Decimal(str(discount_percent))
    subrental_total = Decimal(str(subrental_total))

    order = Order(
        order_number=get_next_order_number(db),
        project_name=project_name.strip(),
        client_id=client_id,
        start_date=start_at.date(),
        end_date=end_at.date(),
        start_at=start_at,
        end_at=end_at,
        shifts=shifts,
        subtotal=Decimal("0"),
        discount_percent=discount_percent,
        status="draft",
        comment=comment,
        client_total=Decimal("0"),
        subrental_total=subrental_total,
        expenses_total=Decimal("0"),
        profit_total=Decimal("0") - subrental_total,
        payment_status="unpaid",
        paid_total=Decimal("0"),
        debt_total=Decimal("0"),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def get_last_order(db: Session) -> Order | None:
    stmt = (
        select(Order)
        .options(
            selectinload(Order.client),
            selectinload(Order.items).selectinload(OrderItem.model),
        )
        .order_by(Order.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_order_by_number(db: Session, order_number: int) -> Order | None:
    stmt = (
        select(Order)
        .options(
            selectinload(Order.client),
            selectinload(Order.items).selectinload(OrderItem.model),
        )
        .where(Order.order_number == order_number)
    )
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

    subtotal = sum(float(item.unit_price_client) * item.qty for item in items)
    discount_percent = float(order.discount_percent or 0)
    discount_amount = subtotal * discount_percent / 100
    client_total = subtotal - discount_amount
    subrental_total = float(order.subrental_total or 0)

    order.subtotal = subtotal
    order.client_total = client_total
    order.profit_total = client_total - subrental_total
    order.debt_total = client_total - float(order.paid_total)

    db.commit()
    db.refresh(order)
