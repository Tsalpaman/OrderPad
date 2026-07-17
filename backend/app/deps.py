"""Shared FastAPI dependencies: DB session, current user, admin guard."""
from fastapi import Depends, Header, HTTPException

from .database import SessionLocal
from .models import User
from .security import read_token


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(authorization: str = Header(default=""),
                     db=Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    data = read_token(authorization.removeprefix("Bearer ").strip())
    if not data:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, data["uid"])
    if not user or not user.active:
        raise HTTPException(401, "Unknown or deactivated user")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    return user
