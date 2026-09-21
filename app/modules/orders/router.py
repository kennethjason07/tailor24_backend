"""Orders router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_customer, require_hub_ops
from app.modules.orders.schemas import OrderCreateRequest
from app.modules.orders.service import OrdersService

router = APIRouter()


def get_svc():
    return OrdersService(get_db())


@router.post("", summary="Create a new order (customer)")
def create_order(
    body: OrderCreateRequest,
    current_user: dict = Depends(require_customer),
    svc: OrdersService = Depends(get_svc),
):
    garment_items = []
    for g in body.garments:
        garment_items.append({
            "type": g.type.value,
            "gender": g.gender.value,
            "serviceCharge": g.serviceCharge,
            "measurements": g.measurements.model_dump(),
            "notes": g.notes,
        })

    result = svc.create_order(
        customer_id=str(current_user["_id"]),
        address_id=body.addressId,
        hub_id=body.hubId,
        pickup_slot=body.pickupSlot.model_dump(),
        payment_method=body.paymentMethod.value,
        garment_items=garment_items,
    )
    return ok(data=result, message="Order created successfully")


@router.get("/my", summary="My orders (customer)")
def my_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_customer),
    svc: OrdersService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    orders = svc.list_orders(customer_id=str(current_user["_id"]), skip=skip, limit=page_size)
    return ok(data=orders)


@router.get("", summary="List orders (hub ops)")
def list_orders(
    hub_id: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: dict = Depends(require_hub_ops),
    svc: OrdersService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    orders = svc.list_orders(hub_id=hub_id, skip=skip, limit=page_size)
    return ok(data=orders)


@router.get("/{order_id}/tracking", summary="Get order tracking (public)")
def get_tracking(
    order_id: str,
    svc: OrdersService = Depends(get_svc),
):
    return ok(data=svc.get_order_tracking(order_id))


@router.get("/{order_id}", summary="Get order by ID")
def get_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
    svc: OrdersService = Depends(get_svc),
):
    role = current_user.get("role")
    customer_id = str(current_user["_id"]) if role == "CUSTOMER" else None
    order = svc.get_order(order_id, customer_id=customer_id)
    return ok(data=order)
