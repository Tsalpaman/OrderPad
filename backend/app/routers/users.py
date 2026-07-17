"""Admin management of staff accounts (names, PINs, roles, on/off)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..deps import get_db, require_admin
from ..models import Order, User
from ..schemas import UserAdminOut, UserCreateIn, UserPatchIn
from ..security import hash_pin

router = APIRouter(tags=["users"])


def _pin_taken(db, pin: str, exclude_id: int | None = None) -> bool:
    """Login is by PIN alone, so two people can never share one."""
    query = select(User).where(User.pin_hash == hash_pin(pin))
    if exclude_id is not None:
        query = query.where(User.id != exclude_id)
    return db.scalar(query.limit(1)) is not None


def _other_active_admins(db, user_id: int) -> int:
    return len(db.scalars(select(User).where(
        User.role == "admin", User.active.is_(True),
        User.id != user_id)).all())


@router.get("/users", response_model=list[UserAdminOut])
def list_users(db=Depends(get_db), _=Depends(require_admin)):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("/users", response_model=UserAdminOut, status_code=201)
def create_user(body: UserCreateIn, db=Depends(get_db),
                _=Depends(require_admin)):
    if _pin_taken(db, body.pin):
        raise HTTPException(422, "This PIN is already in use - pick another")
    user = User(name=body.name, role=body.role, pin_hash=hash_pin(body.pin))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def update_user(user_id: int, body: UserPatchIn, db=Depends(get_db),
                _=Depends(require_admin)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    data = body.model_dump(exclude_unset=True)

    new_role = data.get("role")
    demoting = new_role is not None and new_role != "admin"
    deactivating = data.get("active") is False
    losing_admin = (user.role == "admin" and user.active
                    and (demoting or deactivating))
    if losing_admin and _other_active_admins(db, user_id) == 0:
        raise HTTPException(
            422, "The system must keep at least one active admin")

    if "pin" in data:
        pin = data.pop("pin")
        if _pin_taken(db, pin, exclude_id=user_id):
            raise HTTPException(422,
                                "This PIN is already in use - pick another")
        user.pin_hash = hash_pin(pin)
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, db=Depends(get_db), _=Depends(require_admin)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if (user.role == "admin" and user.active
            and _other_active_admins(db, user_id) == 0):
        raise HTTPException(422, "At least one active admin must remain")
    if db.scalar(select(Order).where(Order.user_id == user_id).limit(1)):
        raise HTTPException(
            422, "Staff member has order history - switch them off instead")
    db.delete(user)
    db.commit()
