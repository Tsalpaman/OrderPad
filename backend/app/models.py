"""Data model: who ordered what, at which table, with which options."""
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer,
                        String, Table as SATable)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

ORDER_STATUSES = ("open", "paid")  # "new"/"ready"/"served" = legacy values

# Option groups attached to individual products - the admin ticks, per
# product, which groups apply. Simple and uniform: no category inheritance.
product_option_groups = SATable(
    "product_option_groups", Base.metadata,
    Column("product_id", ForeignKey("products.id"), primary_key=True),
    Column("group_id", ForeignKey("option_groups.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    pin_hash: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(10))  # "admin" | "staff"
    # "off" blocks login but keeps the person's order history intact.
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    sort: Mapped[int] = mapped_column(Integer, default=0)
    products: Mapped[list["Product"]] = relationship(back_populates="category")


class OptionGroup(Base):
    """A question the waiter answers: 'Sugar?', 'Ice?', 'Mixer?'."""
    __tablename__ = "option_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    selection: Mapped[str] = mapped_column(String(10), default="single")  # single|multi
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    # Insertion order, NOT alphabetical: "No sugar / Medium / Sweet" has
    # semantic order that alphabetical sorting would destroy.
    options: Mapped[list["Option"]] = relationship(
        back_populates="group", cascade="all, delete-orphan",
        order_by="[Option.sort, Option.id]")


class Option(Base):
    """One possible answer; `active` lets the admin hide it without deleting."""
    __tablename__ = "options"
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("option_groups.id"))
    name: Mapped[str] = mapped_column(String(60))
    price_delta_cents: Mapped[int] = mapped_column(Integer, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    group: Mapped[OptionGroup] = relationship(back_populates="options")


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    price_cents: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    category: Mapped[Category] = relationship(back_populates="products")
    # Insertion order, NOT alphabetical: the admin decides what the waiter
    # sees first (Sugar before Extras), same as options within a group.
    option_groups: Mapped[list[OptionGroup]] = relationship(
        secondary=product_option_groups,
        order_by="[OptionGroup.sort, OptionGroup.id]")


class Area(Base):
    """A zone of the venue: Upstairs, Downstairs, Beach..."""
    __tablename__ = "areas"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    sort: Mapped[int] = mapped_column(Integer, default=0)


class Table(Base):
    __tablename__ = "tables"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    area_id: Mapped[int | None] = mapped_column(
        ForeignKey("areas.id"), nullable=True)
    area: Mapped[Area | None] = relationship()

    @property
    def area_name(self) -> str | None:
        """Names repeat across areas ("Table 1" exists in every zone), so
        anything shown out of zone context needs the area label too."""
        return self.area.name if self.area else None


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(10), default="open")
    # Local venue time (not UTC), so "today" in the Z report matches the
    # calendar day the staff actually lives in.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    table: Mapped[Table] = relationship()
    user: Mapped[User] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[int] = mapped_column(Integer, default=1)
    note: Mapped[str] = mapped_column(String(120), default="")
    price_cents: Mapped[int] = mapped_column(Integer)  # snapshot
    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()
    options: Mapped[list["OrderItemOption"]] = relationship(
        cascade="all, delete-orphan")


class OrderItemOption(Base):
    """Chosen option, snapshotted (name + delta) at order time."""
    __tablename__ = "order_item_options"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("order_items.id"))
    name: Mapped[str] = mapped_column(String(60))
    price_delta_cents: Mapped[int] = mapped_column(Integer, default=0)
