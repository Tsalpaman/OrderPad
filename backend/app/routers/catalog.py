from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from ..deps import get_current_user, get_db, require_admin
from ..models import Category, OptionGroup, OrderItem, Product
from ..ordering import move_in_list
from ..schemas import (CategoryLiteOut, CategoryOut, MoveIn, NameIn,
                       ProductIn, ProductOut)

router = APIRouter(tags=["catalog"])


def _apply_groups(product: Product, group_ids: list[int] | None, db):
    if group_ids is None:
        return
    groups = db.scalars(
        select(OptionGroup).where(OptionGroup.id.in_(group_ids))).all()
    if len(groups) != len(set(group_ids)):
        raise HTTPException(404, "Unknown option group id")
    product.option_groups = groups


def _group_for_waiter(group: OptionGroup) -> dict:
    """Serialize a group with only its active options."""
    return {"id": group.id, "name": group.name, "selection": group.selection,
            "required": group.required,
            "options": [{"id": o.id, "name": o.name,
                         "price_delta_cents": o.price_delta_cents,
                         "is_default": o.is_default, "active": True}
                        for o in group.options if o.active]}


@router.get("/catalog", response_model=list[CategoryOut])
def get_catalog(db=Depends(get_db), _=Depends(get_current_user)):
    cats = db.scalars(select(Category)
                      .order_by(Category.sort, Category.id)).all()
    result = []
    for c in cats:
        products = []
        for p in sorted(c.products, key=lambda p: p.name):
            if not p.active:
                continue
            groups = [_group_for_waiter(g) for g in p.option_groups]
            groups = [g for g in groups if g["options"]]  # hide empty groups
            products.append({"id": p.id, "name": p.name,
                             "price_cents": p.price_cents, "active": p.active,
                             "category_id": p.category_id,
                             "option_groups": groups})
        result.append({"id": c.id, "name": c.name, "products": products})
    return result


@router.post("/categories", response_model=CategoryLiteOut, status_code=201)
def create_category(body: NameIn, db=Depends(get_db), _=Depends(require_admin)):
    category = Category(name=body.name)
    max_sort = db.scalar(select(func.max(Category.sort)))
    category.sort = 0 if max_sort is None else max_sort + 1
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.patch("/categories/{category_id}", response_model=CategoryLiteOut)
def rename_category(category_id: int, body: NameIn,
                    db=Depends(get_db), _=Depends(require_admin)):
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(404, "Category not found")
    category.name = body.name
    db.commit()
    db.refresh(category)
    return category


@router.post("/categories/{category_id}/move")
def move_category(category_id: int, body: MoveIn,
                  db=Depends(get_db), _=Depends(require_admin)):
    categories = db.scalars(
        select(Category).order_by(Category.sort, Category.id)).all()
    move_in_list(db, categories, category_id, body.direction)
    return {"ok": True}


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int, db=Depends(get_db),
                    _=Depends(require_admin)):
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(404, "Category not found")
    if category.products:
        raise HTTPException(
            422, "Category still has products - move or delete them first")
    category.option_groups = []
    db.delete(category)
    db.commit()


@router.get("/products", response_model=list[ProductOut])
def all_products(db=Depends(get_db), _=Depends(require_admin)):
    return db.scalars(select(Product).order_by(Product.name)).all()


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(body: ProductIn, db=Depends(get_db), _=Depends(require_admin)):
    if not db.get(Category, body.category_id):
        raise HTTPException(404, "Category not found")
    data = body.model_dump()
    group_ids = data.pop("option_group_ids")
    product = Product(**data)
    _apply_groups(product, group_ids, db)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductIn,
                   db=Depends(get_db), _=Depends(require_admin)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    data = body.model_dump()
    group_ids = data.pop("option_group_ids")
    for key, value in data.items():
        setattr(product, key, value)
    _apply_groups(product, group_ids, db)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, db=Depends(get_db),
                   _=Depends(require_admin)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    if db.scalar(select(OrderItem)
                 .where(OrderItem.product_id == product_id).limit(1)):
        raise HTTPException(
            422, "Product has order history - toggle it off instead")
    product.option_groups = []
    db.delete(product)
    db.commit()
