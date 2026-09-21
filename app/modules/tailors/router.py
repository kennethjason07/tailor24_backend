"""Tailors router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_hub_ops, require_tailor
from app.modules.tailors.schemas import (
    TailorAvailabilityUpdate,
    TailorLocationUpdate,
    TailorProfileCreateRequest,
    TailorProfileUpdateRequest,
)
from app.modules.tailors.service import TailorsService

router = APIRouter()


def get_svc():
    return TailorsService(get_db())


@router.post("/profile", summary="Create tailor profile")
def create_profile(
    body: TailorProfileCreateRequest,
    current_user: dict = Depends(require_tailor),
    svc: TailorsService = Depends(get_svc),
):
    data = body.model_dump()
    data["genderSpecialization"] = [g.value if hasattr(g, "value") else g for g in data["genderSpecialization"]]
    data["skills"] = [s.value if hasattr(s, "value") else s for s in data["skills"]]
    profile = svc.create_profile(str(current_user["_id"]), data)
    return ok(data=profile, message="Tailor profile created")


@router.get("/profile/me", summary="Get my tailor profile")
def get_my_profile(
    current_user: dict = Depends(require_tailor),
    svc: TailorsService = Depends(get_svc),
):
    profile = svc.get_profile_by_user(str(current_user["_id"]))
    return ok(data=profile)


@router.patch("/profile/me", summary="Update my tailor profile")
def update_my_profile(
    body: TailorProfileUpdateRequest,
    current_user: dict = Depends(require_tailor),
    svc: TailorsService = Depends(get_svc),
):
    updates = body.model_dump(exclude_none=True)
    if "genderSpecialization" in updates:
        updates["genderSpecialization"] = [g.value if hasattr(g, "value") else g for g in updates["genderSpecialization"]]
    if "skills" in updates:
        updates["skills"] = [s.value if hasattr(s, "value") else s for s in updates["skills"]]
    if "availability" in updates and hasattr(updates["availability"], "value"):
        updates["availability"] = updates["availability"].value
    profile = svc.update_profile(str(current_user["_id"]), updates)
    return ok(data=profile, message="Profile updated")


@router.patch("/availability", summary="Set my availability")
def set_availability(
    body: TailorAvailabilityUpdate,
    current_user: dict = Depends(require_tailor),
    svc: TailorsService = Depends(get_svc),
):
    profile = svc.update_availability(str(current_user["_id"]), body.availability.value)
    return ok(data=profile, message="Availability updated")


@router.patch("/location", summary="Update my live location")
def update_location(
    body: TailorLocationUpdate,
    current_user: dict = Depends(require_tailor),
    svc: TailorsService = Depends(get_svc),
):
    location = body.location.model_dump()
    profile = svc.update_location(str(current_user["_id"]), location)
    return ok(data=profile, message="Location updated")


@router.get("", summary="List tailors (hub ops)")
def list_tailors(
    hub_id: str = Query(None),
    availability: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: dict = Depends(require_hub_ops),
    svc: TailorsService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    profiles = svc.list_profiles(hub_id=hub_id, availability=availability, skip=skip, limit=page_size)
    return ok(data=profiles)


@router.get("/{profile_id}", summary="Get tailor profile by ID")
def get_profile(
    profile_id: str,
    _: dict = Depends(get_current_user),
    svc: TailorsService = Depends(get_svc),
):
    return ok(data=svc.get_profile(profile_id))
