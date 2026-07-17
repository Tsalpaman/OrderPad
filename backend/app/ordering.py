"""Manual up/down reordering for sortable lists (categories, areas,
option groups, options). Sorts are normalized to list positions first so
legacy ties can never make an arrow press ambiguous."""
from fastapi import HTTPException


def move_in_list(db, items: list, target_id: int, direction: str) -> None:
    ids = [item.id for item in items]
    if target_id not in ids:
        raise HTTPException(404, "Not found")
    index = ids.index(target_id)
    other = index - 1 if direction == "up" else index + 1
    if not 0 <= other < len(items):
        return  # already at the edge - a no-op, not an error
    for position, item in enumerate(items):
        item.sort = position
    items[index].sort, items[other].sort = other, index
    db.commit()
