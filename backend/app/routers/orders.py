from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from ..deps import get_current_user, get_db, require_admin
from ..models import Order, OrderItem, OrderItemOption, Product, Table, User
from ..schemas import (OrderIn, OrderOut, SettleOut, SummaryOut, TableMoveIn,
                       TransferOut, ZOut)
from ..ws import manager

router = APIRouter(tags=["orders"])

# One open tab per table: orders stay individual rows (so the Z report keeps
# per-waiter accuracy) but are grouped per table in the UI and closed
# together by /tables/{id}/settle. "served" is a legacy closed status.
CLOSED_STATUSES = ("paid", "served")


def _order_total(order: Order) -> int:
    return sum(
        (i.price_cents + sum(o.price_delta_cents for o in i.options)) * i.qty
        for i in order.items)


def _order_out(order: Order) -> dict:
    items = [{"name": i.product.name, "qty": i.qty, "note": i.note,
              "price_cents": i.price_cents,
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
            "total_cents": _order_total(order)}


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
    db.delete(order)
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
    total = sum(_order_total(o) for o in orders)
    for order in orders:
        db.delete(order)
    db.commit()
    if orders:
        await manager.broadcast({"type": "table.cancelled",
                                 "table_id": table_id})
    return {"table_id": table_id, "orders_closed": len(orders),
            "total_cents": total}


@router.post("/tables/{table_id}/settle", response_model=SettleOut)
async def settle_table(table_id: int, db=Depends(get_db),
                       _=Depends(get_current_user)):
    """Close the whole tab: mark every open order on the table as paid.
    Idempotent - settling an already-clear table just reports zero."""
    if not db.get(Table, table_id):
        raise HTTPException(404, "Table not found")
    orders = _open_orders(db, table_id)
    total = sum(_order_total(o) for o in orders)
    for order in orders:
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


def _today_orders(db):
    start = datetime.combine(date.today(), time.min)
    return db.scalars(select(Order).where(Order.created_at >= start)).all()


@router.get("/summary", response_model=SummaryOut)
def summary(db=Depends(get_db), _=Depends(require_admin)):
    orders = _today_orders(db)
    start = datetime.combine(date.today(), time.min)
    top = db.execute(
        select(Product.name, func.sum(OrderItem.qty).label("qty"))
        .join(OrderItem.product).join(OrderItem.order)
        .where(Order.created_at >= start)
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
