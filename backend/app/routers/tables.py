from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from ..deps import get_current_user, get_db, require_admin
from ..models import Area, Order, Table
from ..ordering import move_in_list
from ..schemas import (AreaOut, MoveIn, NameIn, TableIn, TableOut,
                       TablePatch)

router = APIRouter(tags=["tables"])


# ---- areas (zones of the venue) ----
@router.get("/areas", response_model=list[AreaOut])
def get_areas(db=Depends(get_db), _=Depends(get_current_user)):
    return db.scalars(select(Area).order_by(Area.sort, Area.id)).all()


@router.post("/areas", response_model=AreaOut, status_code=201)
def create_area(body: NameIn, db=Depends(get_db), _=Depends(require_admin)):
    area = Area(name=body.name)
    max_sort = db.scalar(select(func.max(Area.sort)))
    area.sort = 0 if max_sort is None else max_sort + 1
    db.add(area)
    db.commit()
    db.refresh(area)
    return area


@router.patch("/areas/{area_id}", response_model=AreaOut)
def rename_area(area_id: int, body: NameIn,
                db=Depends(get_db), _=Depends(require_admin)):
    area = db.get(Area, area_id)
    if not area:
        raise HTTPException(404, "Area not found")
    area.name = body.name
    db.commit()
    db.refresh(area)
    return area


@router.post("/areas/{area_id}/move")
def move_area(area_id: int, body: MoveIn,
              db=Depends(get_db), _=Depends(require_admin)):
    areas = db.scalars(select(Area).order_by(Area.sort, Area.id)).all()
    move_in_list(db, areas, area_id, body.direction)
    return {"ok": True}


@router.delete("/areas/{area_id}", status_code=204)
def delete_area(area_id: int, db=Depends(get_db), _=Depends(require_admin)):
    area = db.get(Area, area_id)
    if not area:
        raise HTTPException(404, "Area not found")
    if db.scalar(select(Table).where(Table.area_id == area_id).limit(1)):
        raise HTTPException(
            422, "Area still has tables - move or delete them first")
    db.delete(area)
    db.commit()


# ---- tables ----
@router.get("/tables", response_model=list[TableOut])
def get_tables(db=Depends(get_db), _=Depends(get_current_user)):
    return db.scalars(select(Table).order_by(Table.id)).all()


def _check_area(area_id: int | None, db):
    if area_id is not None and not db.get(Area, area_id):
        raise HTTPException(404, "Area not found")


@router.post("/tables", response_model=TableOut, status_code=201)
def create_table(body: TableIn, db=Depends(get_db), _=Depends(require_admin)):
    _check_area(body.area_id, db)
    table = Table(name=body.name, area_id=body.area_id)
    db.add(table)
    db.commit()
    db.refresh(table)
    return table


@router.patch("/tables/{table_id}", response_model=TableOut)
def update_table(table_id: int, body: TablePatch,
                 db=Depends(get_db), _=Depends(require_admin)):
    table = db.get(Table, table_id)
    if not table:
        raise HTTPException(404, "Table not found")
    data = body.model_dump(exclude_unset=True)
    if "area_id" in data:
        if data["area_id"] is None:
            raise HTTPException(422, "A table must belong to an area")
        _check_area(data["area_id"], db)
    for key, value in data.items():
        setattr(table, key, value)
    db.commit()
    db.refresh(table)
    return table


@router.delete("/tables/{table_id}", status_code=204)
def delete_table(table_id: int, db=Depends(get_db), _=Depends(require_admin)):
    table = db.get(Table, table_id)
    if not table:
        raise HTTPException(404, "Table not found")
    if db.scalar(select(Order).where(Order.table_id == table_id).limit(1)):
        raise HTTPException(
            422, "Table has order history - it cannot be deleted")
    db.delete(table)
    db.commit()
