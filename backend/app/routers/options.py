"""Admin management of option groups, options, and category attachment."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from ..deps import get_db, require_admin
from ..models import Option, OptionGroup
from ..ordering import move_in_list
from ..schemas import (MoveIn, OptionGroupIn, OptionGroupOut,
                       OptionGroupPatch, OptionIn, OptionOut, OptionPatch)

router = APIRouter(tags=["options"])


@router.get("/option-groups", response_model=list[OptionGroupOut])
def list_groups(db=Depends(get_db), _=Depends(require_admin)):
    return db.scalars(select(OptionGroup)
                      .order_by(OptionGroup.sort, OptionGroup.id)).all()


@router.post("/option-groups", response_model=OptionGroupOut, status_code=201)
def create_group(body: OptionGroupIn, db=Depends(get_db), _=Depends(require_admin)):
    group = OptionGroup(**body.model_dump())
    # Append at the end so admin-entered order is what the waiter sees.
    max_sort = db.scalar(select(func.max(OptionGroup.sort)))
    group.sort = 0 if max_sort is None else max_sort + 1
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.patch("/option-groups/{group_id}", response_model=OptionGroupOut)
def update_group(group_id: int, body: OptionGroupPatch,
                 db=Depends(get_db), _=Depends(require_admin)):
    group = db.get(OptionGroup, group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(group, key, value)
    db.commit()
    db.refresh(group)
    return group


@router.post("/option-groups/{group_id}/move")
def move_group(group_id: int, body: MoveIn,
               db=Depends(get_db), _=Depends(require_admin)):
    groups = db.scalars(select(OptionGroup)
                        .order_by(OptionGroup.sort, OptionGroup.id)).all()
    move_in_list(db, groups, group_id, body.direction)
    return {"ok": True}


@router.delete("/option-groups/{group_id}", status_code=204)
def delete_group(group_id: int, db=Depends(get_db), _=Depends(require_admin)):
    group = db.get(OptionGroup, group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    db.delete(group)
    db.commit()


@router.post("/option-groups/{group_id}/options",
             response_model=OptionOut, status_code=201)
def add_option(group_id: int, body: OptionIn,
               db=Depends(get_db), _=Depends(require_admin)):
    group = db.get(OptionGroup, group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    option = Option(group_id=group_id, **body.model_dump())
    # Append at the end of the group so admin-entered order is preserved.
    option.sort = max((o.sort for o in group.options), default=-1) + 1
    db.add(option)
    db.commit()
    db.refresh(option)
    return option


@router.patch("/options/{option_id}", response_model=OptionOut)
def update_option(option_id: int, body: OptionPatch,
                  db=Depends(get_db), _=Depends(require_admin)):
    option = db.get(Option, option_id)
    if not option:
        raise HTTPException(404, "Option not found")
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(option, key, value)
    # In a "pick one" group there can be only one default.
    if data.get("is_default") and option.group.selection == "single":
        for sibling in option.group.options:
            if sibling.id != option.id:
                sibling.is_default = False
    db.commit()
    db.refresh(option)
    return option


@router.post("/options/{option_id}/move")
def move_option(option_id: int, body: MoveIn,
                db=Depends(get_db), _=Depends(require_admin)):
    option = db.get(Option, option_id)
    if not option:
        raise HTTPException(404, "Option not found")
    move_in_list(db, list(option.group.options), option_id, body.direction)
    return {"ok": True}


@router.delete("/options/{option_id}", status_code=204)
def delete_option(option_id: int, db=Depends(get_db), _=Depends(require_admin)):
    option = db.get(Option, option_id)
    if not option:
        raise HTTPException(404, "Option not found")
    db.delete(option)
    db.commit()
