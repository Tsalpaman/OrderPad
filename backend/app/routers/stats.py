"""Read-only analytics for the admin, computed straight from order history:
a revenue trend, peak-hour detection, a Pareto (80/20) product breakdown,
and product affinity (which items sell together). No external service - just
aggregation algorithms over the data we already store."""
from collections import defaultdict
from datetime import date, timedelta
from itertools import combinations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from ..deps import get_db, require_admin
from ..models import Order

router = APIRouter(tags=["stats"])


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
