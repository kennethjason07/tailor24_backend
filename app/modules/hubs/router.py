"""Hubs router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin_finance, require_hub_manager
from app.modules.hubs.schemas import HubCreateRequest, HubUpdateRequest, HubManagerCreateRequest
from app.modules.hubs.service import HubsService

router = APIRouter()


def get_svc():
    return HubsService(get_db())


@router.post("", summary="Create a hub (admin only)")
def create_hub(
    body: HubCreateRequest,
    _: dict = Depends(require_admin_finance),
    svc: HubsService = Depends(get_svc),
):
    data = body.model_dump()
    hub = svc.create_hub(data)
    return ok(data=hub, message="Hub created")


@router.get("", summary="List all hubs")
def list_hubs(
    active_only: bool = Query(True),
    _: dict = Depends(get_current_user),
    svc: HubsService = Depends(get_svc),
):
    return ok(data=svc.list_hubs(active_only))


@router.get("/{hub_id}", summary="Get hub by ID")
def get_hub(
    hub_id: str,
    _: dict = Depends(get_current_user),
    svc: HubsService = Depends(get_svc),
):
    return ok(data=svc.get_hub(hub_id))


@router.patch("/{hub_id}", summary="Update hub")
def update_hub(
    hub_id: str,
    body: HubUpdateRequest,
    _: dict = Depends(require_admin_finance),
    svc: HubsService = Depends(get_svc),
):
    updates = body.model_dump(exclude_none=True)
    hub = svc.update_hub(hub_id, updates)
    return ok(data=hub, message="Hub updated")


@router.delete("/{hub_id}", summary="Delete hub (admin only)")
def delete_hub(
    hub_id: str,
    _: dict = Depends(require_admin_finance),
    svc: HubsService = Depends(get_svc),
):
    svc.delete_hub(hub_id)
    return ok(message="Hub deleted successfully")


@router.post("/{hub_id}/manager", summary="Create or assign hub manager with credentials (admin only)")
def create_hub_manager(
    hub_id: str,
    body: HubManagerCreateRequest,
    _: dict = Depends(require_admin_finance),
    svc: HubsService = Depends(get_svc),
):
    data = body.model_dump()
    manager = svc.create_hub_manager(hub_id, data)
    return ok(data=manager, message="Hub manager created and assigned successfully")
