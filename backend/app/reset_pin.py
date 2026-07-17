"""Emergency rescue: reset a user's PIN - and, if the system has no admin
left, restore one - straight from the shop PC.

    python -m app.reset_pin 9999                    # reset the first admin
    python -m app.reset_pin 1234 Maria             # reset a specific person
    python -m app.reset_pin 9999 Christos --admin  # also make them an admin

If NO active admin exists, the targeted user is promoted to admin
automatically, so you can never be permanently locked out.
"""
import sys

from sqlalchemy import select

from . import migrate
from .database import SessionLocal
from .models import User
from .security import hash_pin


def main():
    args = sys.argv[1:]
    positional = [a for a in args if not a.startswith("--")]
    force_admin = "--admin" in args

    if (not positional or not positional[0].isdigit()
            or not 4 <= len(positional[0]) <= 8):
        print("Usage: python -m app.reset_pin <4-8 digit PIN> [name] [--admin]")
        sys.exit(1)
    pin = positional[0]
    name = positional[1] if len(positional) > 1 else None

    migrate.run()
    db = SessionLocal()
    try:
        users = db.scalars(select(User)).all()
        if name:
            target = next((u for u in users
                           if u.name.lower() == name.lower()), None)
        else:
            target = next((u for u in users if u.role == "admin"), None)
        if not target:
            print("User not found. Tip: pass a name, e.g.\n"
                  "  python -m app.reset_pin 9999 Christos --admin")
            sys.exit(1)
        if any(u.id != target.id and u.pin_hash == hash_pin(pin)
               for u in users):
            print("That PIN already belongs to someone else - pick another.")
            sys.exit(1)

        no_other_admin = not any(
            u.active and u.role == "admin" and u.id != target.id
            for u in users)
        promoted = force_admin or no_other_admin
        if promoted:
            target.role = "admin"

        target.pin_hash = hash_pin(pin)
        target.active = True
        db.commit()
        extra = " and is now an admin" if promoted else ""
        print(f"Done: {target.name} ({target.role}) can now log in "
              f"with PIN {pin}{extra}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
