"""Addresses router."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import require_customer
from app.modules.addresses.schemas import AddressCreateRequest, AddressUpdateRequest
from app.modules.addresses.service import AddressesService

router = APIRouter()


def get_svc():
    return AddressesService(get_db())


@router.post("", summary="Add a new address")
def create_address(
    body: AddressCreateRequest,
    current_user: dict = Depends(require_customer),
    svc: AddressesService = Depends(get_svc),
):
    customer_id = str(current_user["_id"])
    data = body.model_dump()
    if data.get("location"):
        data["location"] = data["location"]
    address = svc.create_address(customer_id, data)
    return ok(data=address, message="Address created")


@router.get("", summary="List customer addresses")
def list_addresses(
    current_user: dict = Depends(require_customer),
    svc: AddressesService = Depends(get_svc),
):
    addresses = svc.list_addresses(str(current_user["_id"]))
    return ok(data=addresses)


@router.get("/{address_id}", summary="Get address by ID")
def get_address(
    address_id: str,
    current_user: dict = Depends(require_customer),
    svc: AddressesService = Depends(get_svc),
):
    address = svc.get_address(address_id, str(current_user["_id"]))
    return ok(data=address)


@router.patch("/{address_id}", summary="Update address")
def update_address(
    address_id: str,
    body: AddressUpdateRequest,
    current_user: dict = Depends(require_customer),
    svc: AddressesService = Depends(get_svc),
):
    updates = body.model_dump(exclude_none=True)
    address = svc.update_address(address_id, str(current_user["_id"]), updates)
    return ok(data=address, message="Address updated")


@router.delete("/{address_id}", summary="Delete address")
def delete_address(
    address_id: str,
    current_user: dict = Depends(require_customer),
    svc: AddressesService = Depends(get_svc),
):
    svc.delete_address(address_id, str(current_user["_id"]))
    return ok(message="Address deleted")
