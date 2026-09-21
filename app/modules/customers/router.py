"""Customers router — customer profile and order history."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import require_customer, require_hub_ops
from app.common.utils import doc_to_dict, to_object_id

router = APIRouter()


@router.get("/me", summary="Get my customer profile")
def get_my_profile(current_user: dict = Depends(require_customer)):
    d = doc_to_dict(current_user)
    d.pop("passwordHash", None)
    return ok(data=d)


@router.get("/{customer_id}", summary="Get customer profile (hub staff/manager)")
def get_customer(
    customer_id: str,
    _: dict = Depends(require_hub_ops),
):
    db = get_db()
    user = db.users.find_one({"_id": to_object_id(customer_id), "role": "CUSTOMER"})
    if not user:
        from app.common.exceptions import NotFoundError
        raise NotFoundError(f"Customer {customer_id} not found.")
    d = doc_to_dict(user)
    d.pop("passwordHash", None)
    return ok(data=d)
