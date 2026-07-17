"""Demo data: menu, users, tables + option groups. Idempotent per section,
so rerunning it on an existing database only fills in what's missing.
Option groups are attached directly to products (uniform, admin-editable
from the Menu table) - no category-level inheritance."""
from sqlalchemy import select, update

from . import migrate
from .database import SessionLocal
from .models import (Area, Category, Option, OptionGroup, Product, Table,
                     User)
from .security import hash_pin

MENU = {
    "Coffee": [("Espresso", 200), ("Double Espresso", 280),
               ("Freddo Espresso", 320), ("Freddo Cappuccino", 350),
               ("Cappuccino", 330), ("Filter Coffee", 300)],
    "Beverages": [("Fresh Orange Juice", 400), ("Iced Tea Peach", 350),
                  ("Sparkling Water 330ml", 250), ("Cola 330ml", 300)],
    "Beer & Wine": [("Lager 500ml", 450), ("IPA 330ml", 550),
                    ("House White (glass)", 500), ("House Red (glass)", 500)],
    "Snacks": [("Club Sandwich", 750), ("Toast Ham & Cheese", 380),
               ("Greek Salad", 700), ("Fries", 400)],
}

USERS = [("Admin", "9999", "admin"), ("Maria", "1111", "waiter"),
         ("Nikos", "2222", "bar")]

# (area name, number of tables) - every area numbers its own tables
AREAS = [("Upstairs", 10), ("Downstairs", 24), ("Beach", 40)]

OPTION_GROUPS = [
    # (name, selection, required, [(option, delta_cents, is_default)])
    ("Sugar", "single", True, [("No sugar", 0, False), ("Medium", 0, True),
                               ("Sweet", 0, False)]),
    ("Ice", "single", False, [("Normal ice", 0, True), ("Light ice", 0, False),
                              ("Extra ice", 0, False)]),
    ("Extras", "multi", False, [("Cinnamon", 0, False), ("Chocolate", 0, False),
                                ("Extra shot", 50, False),
                                ("Vanilla syrup", 30, False)]),
]


def _seed_menu(db):
    for name, pin, role in USERS:
        db.add(User(name=name, pin_hash=hash_pin(pin), role=role))
    for sort, (cat_name, products) in enumerate(MENU.items()):
        cat = Category(name=cat_name, sort=sort)
        db.add(cat)
        db.flush()
        for pname, cents in products:
            db.add(Product(name=pname, price_cents=cents, category_id=cat.id))



def _seed_tables(db, areas):
    # Autonomous per-area numbering: each zone has its own "Table 1..N".
    for (area_name, count), area in zip(AREAS, areas):
        for n in range(1, count + 1):
            db.add(Table(name=f"Table {n}", area_id=area.id))


def _assign_orphan_tables(db):
    """There is no 'Other' bucket: legacy tables without an area are
    adopted by the first area so nothing becomes invisible."""
    first = db.scalars(select(Area).order_by(Area.sort, Area.id)).first()
    if first:
        db.execute(update(Table).where(Table.area_id.is_(None))
                   .values(area_id=first.id))


def _seed_options(db):
    groups = {}
    for sort, (name, selection, required, options) in enumerate(OPTION_GROUPS):
        group = OptionGroup(name=name, selection=selection,
                            required=required, sort=sort)
        db.add(group)
        db.flush()
        for osort, (oname, delta, default) in enumerate(options):
            db.add(Option(group_id=group.id, name=oname,
                          price_delta_cents=delta, is_default=default,
                          sort=osort))
        groups[name] = group

    # Attach directly to matching products - admin can add/remove per
    # product any time from the Menu table's "Extra options" picker.
    for product in db.scalars(select(Product)).all():
        if product.category.name == "Coffee":
            product.option_groups.extend([groups["Sugar"], groups["Extras"]])
        if "Freddo" in product.name or "Iced" in product.name:
            product.option_groups.append(groups["Ice"])


def run():
    migrate.run()
    db = SessionLocal()
    try:
        seeded = []
        if not db.scalar(select(User).limit(1)):
            _seed_menu(db)
            seeded.append("menu & users")
        if not db.scalar(select(Area).limit(1)):
            tables_empty = not db.scalar(select(Table).limit(1))
            areas = []
            for sort, (area_name, count) in enumerate(AREAS):
                area = Area(name=area_name, sort=sort)
                db.add(area)
                db.flush()
                areas.append(area)
            if tables_empty:
                _seed_tables(db, areas)
                seeded.append("areas & 74 tables")
            else:
                seeded.append("areas (existing tables -> Upstairs)")
        if not db.scalar(select(OptionGroup).limit(1)):
            _seed_options(db)
            seeded.append("option groups")
        _assign_orphan_tables(db)
        db.commit()
        if seeded:
            print("Seeded:", " + ".join(seeded),
                  "- PINs 9999 (admin) / 1111 / 2222 (staff)")
        else:
            print("Seed skipped: database already has data.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
