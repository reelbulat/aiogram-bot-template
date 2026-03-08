from datetime import datetime, date

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    type: Mapped[str] = mapped_column(String(20), default="person", nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)

    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    orders = relationship("Order", back_populates="client")


class EquipmentModel(Base):
    __tablename__ = "equipment_models"
    __table_args__ = (
        UniqueConstraint("name", name="uq_equipment_models_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)

    search_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    daily_rent_price: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    estimated_value: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )

    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
    )

    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    units = relationship("EquipmentUnit", back_populates="model")
    order_items = relationship("OrderItem", back_populates="model")


class EquipmentUnit(Base):
    __tablename__ = "equipment_units"
    __table_args__ = (
        UniqueConstraint("internal_number", name="uq_equipment_units_internal_number"),
        UniqueConstraint("serial_number", name="uq_equipment_units_serial_number"),
        UniqueConstraint("article_number", name="uq_equipment_units_article_number"),
        CheckConstraint("shifts_total >= 0", name="chk_equipment_units_shifts_total"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    model_id: Mapped[int] = mapped_column(
        ForeignKey("equipment_models.id", ondelete="RESTRICT"),
        nullable=False,
    )

    internal_number: Mapped[str] = mapped_column(Text, nullable=False)
    serial_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    article_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    purchase_price: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    estimated_value: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )

    defects: Mapped[str | None] = mapped_column(Text, nullable=True)

    shifts_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue_total: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    profit_total: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")

    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    model = relationship("EquipmentModel", back_populates="units")
    bookings = relationship("Booking", back_populates="equipment_unit")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("order_number", name="uq_orders_order_number"),
        CheckConstraint("shifts > 0", name="chk_orders_shifts"),
        CheckConstraint("end_date >= start_date", name="chk_orders_date_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    order_number: Mapped[int] = mapped_column(Integer, nullable=False)

    project_name: Mapped[str] = mapped_column(Text, nullable=False)

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=False,
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    shifts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    subtotal: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    discount_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    client_total: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    subrental_total: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    expenses_total: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    profit_total: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )

    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unpaid"
    )

    paid_total: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    debt_total: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    client = relationship("Client", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="order", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("qty > 0", name="chk_order_items_qty"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_id: Mapped[int] = mapped_column(
        ForeignKey("equipment_models.id", ondelete="RESTRICT"),
        nullable=False,
    )

    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_client: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )

    is_subrental: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subrental_cost: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )

    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    order = relationship("Order", back_populates="items")
    model = relationship("EquipmentModel", back_populates="order_items")
    bookings = relationship("Booking", back_populates="order_item", cascade="all, delete-orphan")


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="chk_bookings_date_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    equipment_unit_id: Mapped[int] = mapped_column(
        ForeignKey("equipment_units.id", ondelete="RESTRICT"),
        nullable=False,
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reserved")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    order_item = relationship("OrderItem", back_populates="bookings")
    equipment_unit = relationship("EquipmentUnit", back_populates="bookings")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_payments_amount"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="done")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    order = relationship("Order", back_populates="payments")


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="chk_expenses_amount"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    order = relationship("Order", back_populates="expenses")
