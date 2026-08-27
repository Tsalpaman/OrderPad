"""Pydantic shapes for requests/responses."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    pin: str = Field(min_length=4, max_length=8)


class UserOut(BaseModel):
    id: int
    name: str
    role: str


class LoginOut(BaseModel):
    token: str
    user: UserOut


class UserAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    role: str
    active: bool = True


class UserCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")
    role: str = Field(default="waiter", pattern="^(admin|waiter|bar)$")


class UserPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    pin: str | None = Field(default=None, min_length=4, max_length=8,
                            pattern=r"^\d+$")
    role: str | None = Field(default=None, pattern="^(admin|waiter|bar)$")
    active: bool | None = None


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class CategoryLiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


# ---- options ----
class OptionIn(BaseModel):
    name: str
    price_delta_cents: int = 0
    is_default: bool = False
    active: bool = True


class OptionOut(OptionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class OptionPatch(BaseModel):
    name: str | None = None
    price_delta_cents: int | None = None
    is_default: bool | None = None
    active: bool | None = None


class OptionGroupIn(BaseModel):
    name: str
    selection: str = Field(default="single", pattern="^(single|multi)$")
    required: bool = False


class OptionGroupPatch(BaseModel):
    name: str | None = None
    selection: str | None = Field(default=None, pattern="^(single|multi)$")
    required: bool | None = None


class OptionGroupOut(OptionGroupIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    options: list[OptionOut] = []


# ---- catalog ----
class ProductBase(BaseModel):
    name: str
    price_cents: int = Field(ge=0)
    category_id: int
    active: bool = True


class ProductIn(ProductBase):
    option_group_ids: list[int] | None = None  # None = leave unchanged


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    option_groups: list[OptionGroupOut] = []


class CategoryOut(BaseModel):
    id: int
    name: str
    products: list[ProductOut]


class AreaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class TableIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    area_id: int


class TablePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=30)
    area_id: int | None = None


class TableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    area_id: int | None = None
    area_name: str | None = None


# ---- orders ----
class OrderItemIn(BaseModel):
    product_id: int
    qty: int = Field(ge=1, le=50)
    note: str = ""
    option_ids: list[int] = []


class OrderIn(BaseModel):
    table_id: int
    items: list[OrderItemIn] = Field(min_length=1)


class OptionSnapOut(BaseModel):
    name: str
    price_delta_cents: int


class OrderItemOut(BaseModel):
    id: int
    name: str
    qty: int
    note: str
    price_cents: int
    line_total_cents: int
    paid: bool = False
    options: list[OptionSnapOut] = []


class OrderOut(BaseModel):
    id: int
    table: TableOut
    waiter: str
    status: str
    created_at: datetime
    items: list[OrderItemOut]
    total_cents: int
    due_cents: int


class TableMoveIn(BaseModel):
    table_id: int


class MoveIn(BaseModel):
    direction: str = Field(pattern="^(up|down)$")


class SettleOut(BaseModel):
    table_id: int
    orders_closed: int
    total_cents: int


class PayItemsIn(BaseModel):
    item_ids: list[int] = Field(min_length=1)


class PayItemsOut(BaseModel):
    paid_cents: int
    items_paid: int
    table_due_cents: int


class TransferOut(BaseModel):
    from_table_id: int
    to_table_id: int
    orders_moved: int


class SummaryOut(BaseModel):
    orders_today: int
    revenue_cents_today: int
    top_products: list[dict]


# ---- Z report ----
class ZWaiterOut(BaseModel):
    waiter: str
    orders: int
    revenue_cents: int


class ZOut(BaseModel):
    date: str
    waiters: list[ZWaiterOut]
    total_orders: int
    total_revenue_cents: int
