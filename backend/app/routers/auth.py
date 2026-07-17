from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..deps import get_db
from ..models import User
from ..schemas import LoginIn, LoginOut
from ..security import hash_pin, make_token

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db=Depends(get_db)):
    user = db.scalar(select(User).where(User.pin_hash == hash_pin(body.pin)))
    if not user:
        raise HTTPException(401, "Wrong PIN")
    if not user.active:
        raise HTTPException(403, "Account deactivated - ask the admin")
    return {"token": make_token(user.id, user.role),
            "user": {"id": user.id, "name": user.name, "role": user.role}}
