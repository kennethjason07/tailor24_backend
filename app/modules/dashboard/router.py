"""Dashboard router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin_finance, require_hub_manager
from app.modules.dashboard.service import DashboardService

router = APIRouter()


def get_svc():
    return DashboardService(get_db())


@router.get("", summary="Dashboard overview")
def dashboard_overview(
    hub_id: str = Query(None, description="Filter by hub. Admins can pass any hub or omit for franchise-wide."),
    current_user: dict = Depends(get_current_user),
    svc: DashboardService = Depends(get_svc),
):
    role = current_user.get("role")

    # Hub managers can only see their own hub — derive hub from their profile
    if role == "HUB_MANAGER" and not hub_id:
        db = get_db()
        from bson import ObjectId
        hub = db.hubs.find_one({"managerUserId": ObjectId(str(current_user["_id"]))})
        if hub:
            hub_id = str(hub["_id"])

    # Admins can see all or filter by hub_id
    data = svc.get_overview(hub_id=hub_id)
    return ok(data=data)


@router.get("/tailor-capacity", summary="Tailor capacity overview")
def tailor_capacity(
    hub_id: str = Query(None),
    current_user: dict = Depends(get_current_user),
    svc: DashboardService = Depends(get_svc),
):
    role = current_user.get("role")
    if role == "HUB_MANAGER" and not hub_id:
        db = get_db()
        from bson import ObjectId
        hub = db.hubs.find_one({"managerUserId": ObjectId(str(current_user["_id"]))})
        if hub:
            hub_id = str(hub["_id"])
    data = svc.get_tailor_capacity(hub_id=hub_id)
    return ok(data=data)
