"""Deliveries router."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_hub_ops, require_rider
from app.modules.deliveries.service import DeliveriesService

router = APIRouter()


class CreateDeliveryRequest(BaseModel):
    orderId: str
    hubId: str
    riderId: str
    codAmount: Optional[Decimal] = None


class UpdateStatusRequest(BaseModel):
    status: str


class ConfirmDeliveryRequest(BaseModel):
    otp: Optional[str] = None
    codCollected: bool = False


class FailureRequest(BaseModel):
    reason: str


def get_svc():
    return DeliveriesService(get_db())


@router.post("", summary="Create delivery assignment (hub ops)")
def create_delivery(
    body: CreateDeliveryRequest,
    _: dict = Depends(require_hub_ops),
    svc: DeliveriesService = Depends(get_svc),
):
    result = svc.create_delivery(
        order_id=body.orderId,
        hub_id=body.hubId,
        rider_id=body.riderId,
        cod_amount=body.codAmount,
    )
    return ok(data=result, message="Delivery created")


@router.get("/my", summary="My deliveries (rider)")
def my_deliveries(
    status: str = Query(None),
    current_user: dict = Depends(require_rider),
    svc: DeliveriesService = Depends(get_svc),
):
    deliveries = svc.list_rider_deliveries(str(current_user["_id"]), status=status)
    return ok(data=deliveries)


@router.get("/{delivery_id}", summary="Get delivery")
def get_delivery(
    delivery_id: str,
    _: dict = Depends(get_current_user),
    svc: DeliveriesService = Depends(get_svc),
):
    return ok(data=svc.get_delivery(delivery_id))


@router.patch("/{delivery_id}/status", summary="Update delivery status (rider)")
def update_status(
    delivery_id: str,
    body: UpdateStatusRequest,
    current_user: dict = Depends(require_rider),
    svc: DeliveriesService = Depends(get_svc),
):
    delivery = svc.update_status(delivery_id, body.status, str(current_user["_id"]))
    return ok(data=delivery, message="Status updated")


@router.post("/{delivery_id}/confirm", summary="Confirm delivery with OTP (rider)")
def confirm_delivery(
    delivery_id: str,
    body: ConfirmDeliveryRequest,
    current_user: dict = Depends(require_rider),
    svc: DeliveriesService = Depends(get_svc),
):
    delivery = svc.confirm_delivery(
        delivery_id=delivery_id,
        rider_id=str(current_user["_id"]),
        otp=body.otp,
        cod_collected=body.codCollected,
    )
    return ok(data=delivery, message="Delivery confirmed")


@router.post("/{delivery_id}/fail", summary="Mark delivery failed (rider)")
def mark_failed(
    delivery_id: str,
    body: FailureRequest,
    current_user: dict = Depends(require_rider),
    svc: DeliveriesService = Depends(get_svc),
):
    delivery = svc.mark_failed(delivery_id, str(current_user["_id"]), body.reason)
    return ok(data=delivery, message="Delivery marked as failed")
