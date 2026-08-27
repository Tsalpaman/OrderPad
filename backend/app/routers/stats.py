"""Read-only analytics for the admin, computed straight from order history:
a revenue trend, peak-hour detection, a Pareto (80/20) product breakdown,
and product affinity (which items sell together). No external service - just
aggregation algorithms over the data we already store."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from itertools import combinations

import json

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select

from ..deps import get_db, require_admin
from ..models import Order, Setting

router = APIRouter(tags=["stats"])

PANELS = ("summary", "revenue_by_day", "by_hour", "staff", "pareto",
          "affinity")
PANELS_KEY = "stats_panels"


def _panels(db) -> dict:
    """Which stats panels are visible. Anything unknown defaults to on, so
    a panel added in a later version shows up without a migration."""
    row = db.get(Setting, PANELS_KEY)
    saved = json.loads(row.value) if row else {}
    return {p: bool(saved.get(p, True)) for p in PANELS}


@router.get("/stats-settings")
def get_stats_settings(db=Depends(get_db), _=Depends(require_admin)):
    return {"panels": _panels(db)}


@router.patch("/stats-settings")
def set_stats_settings(panels: dict = Body(..., embed=True),
                       db=Depends(get_db), _=Depends(require_admin)):
    current = _panels(db)
    current.update({k: bool(v) for k, v in panels.items() if k in PANELS})
    row = db.get(Setting, PANELS_KEY)
    if row:
        row.value = json.dumps(current)
    else:
        db.add(Setting(key=PANELS_KEY, value=json.dumps(current)))
    db.commit()
    return {"panels": current}


def _line_total(item) -> int:
    return (item.price_cents
            + sum(o.price_delta_cents for o in item.options)) * item.qty


def _order_total(order) -> int:
    return sum(_line_total(i) for i in order.items)


@router.get("/stats")
def stats(days: int = 14, db=Depends(get_db), _=Depends(require_admin)):
    orders = db.scalars(select(Order)).all()
    n = len(orders)
    total_revenue = sum(_order_total(o) for o in orders)

    # --- revenue per day, last `days` calendar days (fills gaps with 0) ---
    today = date.today()
    span = {(today - timedelta(d)).isoformat(): 0 for d in range(days)}
    for o in orders:
        key = o.created_at.date().isoformat()
        if key in span:
            span[key] += _order_total(o)
    revenue_by_day = [{"date": k, "revenue_cents": v}
                      for k, v in sorted(span.items())]

    # --- orders/revenue by hour of day, with peak detection ---
    hour_orders, hour_rev = defaultdict(int), defaultdict(int)
    for o in orders:
        hour_orders[o.created_at.hour] += 1
        hour_rev[o.created_at.hour] += _order_total(o)
    by_hour = [{"hour": h, "orders": hour_orders[h],
                "revenue_cents": hour_rev[h]} for h in range(24)]
    peak_hour = (max(by_hour, key=lambda x: x["orders"])["hour"]
                 if n else None)

    # --- Pareto 80/20: the fewest products that make 80% of revenue ---
    prod_rev, prod_qty = defaultdict(int), defaultdict(int)
    for o in orders:
        for i in o.items:
            prod_rev[i.product.name] += _line_total(i)
            prod_qty[i.product.name] += i.qty
    ranked = sorted(prod_rev.items(), key=lambda x: -x[1])
    cum, pareto, pareto_count = 0, [], 0
    for name, rev in ranked:
        cum += rev
        pct = round(100 * cum / total_revenue, 1) if total_revenue else 0
        pareto.append({"name": name, "revenue_cents": rev,
                       "qty": prod_qty[name], "cumulative_pct": pct})
        if not pareto_count and total_revenue and cum >= 0.8 * total_revenue:
            pareto_count = len(pareto)

    # --- product affinity: top co-occurring pairs (support + lift) ---
    pair, seen = defaultdict(int), defaultdict(int)
    for o in orders:
        names = sorted({i.product.name for i in o.items})
        for name in names:
            seen[name] += 1
        for a, b in combinations(names, 2):
            pair[(a, b)] += 1
    affinity = []
    for (a, b), c in sorted(pair.items(), key=lambda x: -x[1])[:6]:
        support = round(100 * c / n, 1) if n else 0
        pa, pb = seen[a] / n, seen[b] / n
        lift = round((c / n) / (pa * pb), 2) if pa and pb else 0
        affinity.append({"a": a, "b": b, "count": c,
                         "support_pct": support, "lift": lift})

    return {
        "panels": _panels(db),
        "total_orders": n,
        "total_revenue_cents": total_revenue,
        "avg_order_cents": round(total_revenue / n) if n else 0,
        "revenue_by_day": revenue_by_day,
        "by_hour": by_hour,
        "peak_hour": peak_hour,
        "pareto": pareto[:12],
        "pareto_count": pareto_count,
        "pareto_total_products": len(ranked),
        "affinity": affinity,
    }


@router.get("/stats/staff")
def staff_stats(days: int = 30, db=Depends(get_db), _=Depends(require_admin)):
    """Per-waiter performance over the last `days`.

    Beyond raw volume we compute the metrics an owner actually cares about:
    average check, items per order, and - the real upselling signal - the
    attach rate of *paid* extras (options with a price delta), plus the
    revenue those extras generated on their own.
    """
    since = datetime.combine(date.today() - timedelta(days - 1), time.min)
    orders = db.scalars(select(Order).where(Order.created_at >= since)).all()

    per = {}
    for o in orders:
        r = per.setdefault(o.user_id, {
            "waiter": o.user.name, "role": o.user.role, "active": o.user.active,
            "orders": 0, "revenue_cents": 0, "items": 0,
            "orders_with_paid_extra": 0, "extras_revenue_cents": 0,
            "tables": set(), "days": set(), "hours": {},
        })
        r["orders"] += 1
        r["revenue_cents"] += _order_total(o)
        r["tables"].add(o.table_id)
        r["days"].add(o.created_at.date())
        r["hours"][o.created_at.hour] = r["hours"].get(o.created_at.hour, 0) + 1

        paid_extra = False
        for i in o.items:
            r["items"] += i.qty
            for opt in i.options:
                if opt.price_delta_cents > 0:
                    paid_extra = True
                    r["extras_revenue_cents"] += opt.price_delta_cents * i.qty
        if paid_extra:
            r["orders_with_paid_extra"] += 1

    total_revenue = sum(r["revenue_cents"] for r in per.values()) or 0
    rows = []
    for r in per.values():
        n = r["orders"]
        busiest = max(r["hours"], key=r["hours"].get) if r["hours"] else None
        rows.append({
            "waiter": r["waiter"], "role": r["role"], "active": r["active"],
            "orders": n,
            "revenue_cents": r["revenue_cents"],
            "avg_order_cents": round(r["revenue_cents"] / n) if n else 0,
            "items_per_order": round(r["items"] / n, 1) if n else 0,
            "attach_rate_pct": round(100 * r["orders_with_paid_extra"] / n, 1) if n else 0,
            "extras_revenue_cents": r["extras_revenue_cents"],
            "tables_served": len(r["tables"]),
            "days_worked": len(r["days"]),
            "orders_per_day": round(n / len(r["days"]), 1) if r["days"] else 0,
            "busiest_hour": busiest,
            "revenue_share_pct": round(100 * r["revenue_cents"] / total_revenue, 1)
                                 if total_revenue else 0,
        })
    rows.sort(key=lambda x: -x["revenue_cents"])

    team = {
        "avg_order_cents": round(total_revenue / sum(r["orders"] for r in rows))
                           if rows and sum(r["orders"] for r in rows) else 0,
        "attach_rate_pct": round(
            sum(r["attach_rate_pct"] * r["orders"] for r in rows)
            / sum(r["orders"] for r in rows), 1) if rows and sum(r["orders"] for r in rows) else 0,
    }
    return {"days": days, "staff": rows, "team": team,
            "total_revenue_cents": total_revenue}
