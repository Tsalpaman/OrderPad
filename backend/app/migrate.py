"""Tiny additive migrations so an existing SQLite file keeps working across
versions. Called both by the API on startup and by `python -m app.seed`
run standalone, so neither path can skip it."""
from sqlalchemy import inspect, text

from .database import Base, engine


def run():
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if inspector.has_table("options"):
        columns = {c["name"] for c in inspector.get_columns("options")}
        if "active" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE options "
                    "ADD COLUMN active BOOLEAN NOT NULL DEFAULT 1"))
    if inspector.has_table("tables"):
        columns = {c["name"] for c in inspector.get_columns("tables")}
        if "area_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE tables "
                    "ADD COLUMN area_id INTEGER REFERENCES areas(id)"))

    # No "Other" bucket: adopt any orphan tables into the first area.
    if inspector.has_table("tables") and inspector.has_table("areas"):
        with engine.begin() as conn:
            first = conn.execute(text(
                "SELECT id FROM areas ORDER BY sort, id LIMIT 1")).first()
            if first:
                conn.execute(text(
                    "UPDATE tables SET area_id = :area_id "
                    "WHERE area_id IS NULL"), {"area_id": first[0]})

    # v0.14: staff can be deactivated without losing their history.
    if inspector.has_table("users"):
        columns = {c["name"] for c in inspector.get_columns("users")}
        if "active" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE users "
                    "ADD COLUMN active BOOLEAN NOT NULL DEFAULT 1"))

    # v0.20: "staff" splits into waiter (tables only) and bar (tables+bar).
    if inspector.has_table("users"):
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE users SET role='waiter' WHERE role='staff'"))

    # v0.27: cancellation audit trail + per-item (split) payments.
    if inspector.has_table("orders"):
        columns = {c["name"] for c in inspector.get_columns("orders")}
        if "cancelled_at" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE orders ADD COLUMN cancelled_at DATETIME"))
    if inspector.has_table("order_items"):
        columns = {c["name"] for c in inspector.get_columns("order_items")}
        if "paid_at" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE order_items ADD COLUMN paid_at DATETIME"))
