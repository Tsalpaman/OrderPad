from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from ..deps import get_current_user, get_db, require_admin
from ..models import Order, OrderItem, OrderItemOption, Product, Table, User
from ..schemas import (OrderIn, OrderOut, PayItemsIn, PayItemsOut, SettleOut,
                       SummaryOut, TableMoveIn, TransferOut, ZOut)
from ..ws import manager

router = APIRouter(tags=["orders"])

# One open tab per table: orders stay individual rows (so the Z report keeps
# per-waiter accuracy) but are grouped per table in the UI and closed
# together by /tables/{id}/settle. "served" is a legacy closed status.
CLOSED_STATUSES = ("paid", "served", "cancelled")


def _item_total(item: OrderItem) -> int:
    return (item.price_cents
            + sum(o.price_delta_cents for o in item.options)) * item.qty


def _order_total(order: Order) -> int:
    return sum(_item_total(i) for i in order.items)


def _order_due(order: Order) -> int:
    """What is still owed on this order (unpaid lines only)."""
    if order.status in ("paid", "served", "cancelled"):
        return 0
    return sum(_item_total(i) for i in order.items if i.paid_at is None)


def _order_out(order: Order) -> dict:
    items = [{"id": i.id, "name": i.product.name, "qty": i.qty,
              "note": i.note, "price_cents": i.price_cents,
              "line_total_cents": _item_total(i),
              "paid": i.paid_at is not None,
              "options": [{"name": o.name,
                           "price_delta_cents": o.price_delta_cents}
                          for o in i.options]}
             for i in order.items]
    return {"id": order.id,
            "table": {"id": order.table.id, "name": order.table.name,
                      "area_id": order.table.area_id,
                      "area_name": order.table.area_name},
            "waiter": order.user.name,
            "status": order.status,
            "created_at": order.created_at,
            "items": items,
            "total_cents": _order_total(order),
            "due_cents": _order_due(order)}


def _build_item(item_in, db) -> OrderItem:
    product = db.get(Product, item_in.product_id)
    if not product or not product.active:
        raise HTTPException(404, f"Product {item_in.product_id} not available")

    groups = product.option_groups
    allowed = {o.id: (o, g) for g in groups for o in g.options if o.active}
    chosen: list = []
    per_group: dict[int, int] = {}
    for oid in item_in.option_ids:
        if oid not in allowed:
            raise HTTPException(422, f"Option {oid} not valid for {product.name}")
        option, group = allowed[oid]
        per_group[group.id] = per_group.get(group.id, 0) + 1
        if group.selection == "single" and per_group[group.id] > 1:
            raise HTTPException(422, f"Pick only one option for '{group.name}'")
        chosen.append(option)
    for group in groups:
        has_active = any(o.active for o in group.options)
        if group.required and has_active and per_group.get(group.id, 0) == 0:
            raise HTTPException(422, f"'{group.name}' is required for {product.name}")

    return OrderItem(
        product_id=product.id, qty=item_in.qty, note=item_in.note.strip(),
        price_cents=product.price_cents,
        options=[OrderItemOption(name=o.name,
                                 price_delta_cents=o.price_delta_cents)
                 for o in chosen])


def _open_orders(db, table_id: int) -> list[Order]:
    return db.scalars(
        select(Order)
        .where(Order.table_id == table_id,
               Order.status.not_in(CLOSED_STATUSES))
        .order_by(Order.created_at)).all()


@router.post("/orders", response_model=OrderOut, status_code=201)
async def create_order(body: OrderIn, db=Depends(get_db),
                       user: User = Depends(get_current_user)):
    if not db.get(Table, body.table_id):
        raise HTTPException(404, "Table not found")
    order = Order(table_id=body.table_id, user_id=user.id)
    for item_in in body.items:
        order.items.append(_build_item(item_in, db))
    db.add(order)
    db.commit()
    db.refresh(order)
    payload = _order_out(order)
    await manager.broadcast({"type": "order.created",
                             "order": OrderOut(**payload).model_dump(mode="json")})
    return payload


@router.get("/orders", response_model=list[OrderOut])
def list_orders(active: bool = False, db=Depends(get_db),
                _=Depends(get_current_user)):
    query = select(Order).order_by(Order.created_at)
    if active:
        query = query.where(Order.status.not_in(CLOSED_STATUSES))
    return [_order_out(o) for o in db.scalars(query).all()]


@router.delete("/orders/{order_id}", status_code=204)
async def cancel_order(order_id: int, db=Depends(get_db),
                       _=Depends(get_current_user)):
    """Cancel a single round. Only open rounds can go - paid history is
    immutable so the Z report stays truthful."""
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status in CLOSED_STATUSES:
        raise HTTPException(422, "Order is already closed - cannot cancel")
    table_id = order.table_id
    order.status = "cancelled"
    order.cancelled_at = datetime.now()
    db.commit()
    await manager.broadcast({"type": "order.deleted",
                             "order_id": order_id, "table_id": table_id})


@router.post("/tables/{table_id}/cancel", response_model=SettleOut)
async def cancel_table(table_id: int, db=Depends(get_db),
                       _=Depends(get_current_user)):
    """Void every open round on the table (wrong table, walk-out...)."""
    if not db.get(Table, table_id):
        raise HTTPException(404, "Table not found")
    orders = _open_orders(db, table_id)
    total = sum(_order_due(o) for o in orders)
    now = datetime.now()
    for order in orders:
        order.status = "cancelled"
        order.cancelled_at = now
    db.commit()
    if orders:
        await manager.broadcast({"type": "table.cancelled",
                                 "table_id": table_id})
    return {"table_id": table_id, "orders_closed": len(orders),
            "total_cents": total}


@router.post("/order-items/{item_id}/split", response_model=OrderOut)
async def split_item(item_id: int, db=Depends(get_db),
                     _=Depends(get_current_user)):
    """Break a quantity line into single units so guests who ordered the
    same drink can each pay their own. 2x Freddo becomes 1x + 1x."""
    item = db.get(OrderItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    order = item.order
    if order.status in CLOSED_STATUSES:
        raise HTTPException(422, "Order is already closed")
    if item.paid_at is not None:
        raise HTTPException(422, "This line is already paid")
    if item.qty < 2:
        raise HTTPException(422, "Nothing to split - the line is a single item")

    extras = item.qty - 1
    item.qty = 1
    for _copy in range(extras):
        db.add(OrderItem(
            order_id=order.id, product_id=item.product_id, qty=1,
            note=item.note, price_cents=item.price_cents,
            options=[OrderItemOption(name=o.name,
                                     price_delta_cents=o.price_delta_cents)
                     for o in item.options]))
    db.commit()
    db.refresh(order)
    payload = _order_out(order)
    await manager.broadcast({"type": "order.updated",
                             "order": OrderOut(**payload).model_dump(mode="json")})
    return payload


@router.post("/tables/{table_id}/pay-items", response_model=PayItemsOut)
async def pay_items(table_id: int, body: PayItemsIn, db=Depends(get_db),
                    _=Depends(get_current_user)):
    """Split the bill: settle individual lines so one guest can pay their
    own drink while the table's tab stays open for the rest."""
    if not db.get(Table, table_id):
        raise HTTPException(404, "Table not found")
    open_orders = _open_orders(db, table_id)
    lines = {i.id: (i, o) for o in open_orders for i in o.items}

    chosen = []
    for item_id in set(body.item_ids):
        if item_id not in lines:
            raise HTTPException(404, f"Item {item_id} is not on this open tab")
        item, order = lines[item_id]
        if item.paid_at is None:
            chosen.append((item, order))

    now = datetime.now()
    paid_cents = 0
    for item, _order in chosen:
        item.paid_at = now
        paid_cents += _item_total(item)
    # an order whose lines are all settled closes on its own
    for order in open_orders:
        if all(i.paid_at is not None for i in order.items):
            order.status = "paid"
    db.commit()

    remaining = sum(_order_due(o) for o in _open_orders(db, table_id))
    await manager.broadcast({"type": "table.updated", "table_id": table_id})
    return {"paid_cents": paid_cents, "items_paid": len(chosen),
            "table_due_cents": remaining}


@router.post("/tables/{table_id}/settle", response_model=SettleOut)
async def settle_table(table_id: int, db=Depends(get_db),
                       _=Depends(get_current_user)):
    """Close the whole tab: mark every open order on the table as paid.
    Idempotent - settling an already-clear table just reports zero."""
    if not db.get(Table, table_id):
        raise HTTPException(404, "Table not found")
    orders = _open_orders(db, table_id)
    total = sum(_order_due(o) for o in orders)
    now = datetime.now()
    for order in orders:
        for item in order.items:
            if item.paid_at is None:
                item.paid_at = now
        order.status = "paid"
    db.commit()
    if orders:
        await manager.broadcast({"type": "table.settled",
                                 "table_id": table_id})
    return {"table_id": table_id, "orders_closed": len(orders),
            "total_cents": total}


@router.post("/tables/{table_id}/transfer", response_model=TransferOut)
async def transfer_table(table_id: int, body: TableMoveIn,
                         db=Depends(get_db), _=Depends(get_current_user)):
    """Customer changed seats: move every open order to the new table."""
    if not db.get(Table, table_id):
        raise HTTPException(404, "Table not found")
    if not db.get(Table, body.table_id):
        raise HTTPException(404, "Target table not found")
    orders = _open_orders(db, table_id)
    for order in orders:
        order.table_id = body.table_id
    db.commit()
    if orders:
        await manager.broadcast({"type": "table.transferred",
                                 "from_table_id": table_id,
                                 "to_table_id": body.table_id})
    return {"from_table_id": table_id, "to_table_id": body.table_id,
            "orders_moved": len(orders)}


def _today_orders(db, include_cancelled: bool = False):
    start = datetime.combine(date.today(), time.min)
    query = select(Order).where(Order.created_at >= start)
    if not include_cancelled:
        query = query.where(Order.status != "cancelled")
    return db.scalars(query).all()


@router.get("/summary", response_model=SummaryOut)
def summary(db=Depends(get_db), _=Depends(require_admin)):
    orders = _today_orders(db)
    start = datetime.combine(date.today(), time.min)
    top = db.execute(
        select(Product.name, func.sum(OrderItem.qty).label("qty"))
        .join(OrderItem.product).join(OrderItem.order)
        .where(Order.created_at >= start, Order.status != "cancelled")
        .group_by(Product.name).order_by(func.sum(OrderItem.qty).desc())
        .limit(5)).all()
    return {"orders_today": len(orders),
            "revenue_cents_today": sum(_order_total(o) for o in orders),
            "top_products": [{"name": n, "qty": int(q)} for n, q in top]}


@router.get("/reports/z", response_model=ZOut)
def z_report(db=Depends(get_db), _=Depends(require_admin)):
    """End-of-day totals per waiter (the classic 'Z')."""
    per: dict[int, dict] = {}
    orders = _today_orders(db)
    for order in orders:
        record = per.setdefault(order.user_id, {
            "waiter": order.user.name, "orders": 0, "revenue_cents": 0})
        record["orders"] += 1
        record["revenue_cents"] += _order_total(order)
    waiters = sorted(per.values(), key=lambda r: -r["revenue_cents"])
    return {"date": date.today().isoformat(),
            "waiters": waiters,
            "total_orders": len(orders),
            "total_revenue_cents": sum(w["revenue_cents"] for w in waiters)}
