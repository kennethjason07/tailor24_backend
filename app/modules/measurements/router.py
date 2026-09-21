from __future__ import annotations
from typing import List
from fastapi import APIRouter, Depends

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import require_customer, get_current_user, require_hub_ops
from app.modules.measurements.schemas import (
    MeasurementProfileCreateRequest,
    MeasurementProfileUpdateRequest,
    GarmentMeasurementUpdateRequest,
    ClarificationRequest
)
from app.modules.measurements.service import MeasurementsService

router = APIRouter()

def get_svc() -> MeasurementsService:
    return MeasurementsService(get_db())


# ── Customer Measurement Profiles ─────────────────────────────────────────────

@router.post("/customers/measurement-profiles", summary="Create measurement profile")
def create_profile(
    body: MeasurementProfileCreateRequest,
    current_user: dict = Depends(require_customer),
    svc: MeasurementsService = Depends(get_svc)
):
    profile = svc.create_profile(str(current_user["_id"]), body)
    return ok(data=profile, message="Profile created")


@router.get("/customers/measurement-profiles", summary="List own measurement profiles")
def list_profiles(
    current_user: dict = Depends(require_customer),
    svc: MeasurementsService = Depends(get_svc)
):
    profiles = svc.list_profiles(str(current_user["_id"]))
    return ok(data=profiles)


@router.get("/customers/measurement-profiles/{profile_id}", summary="Get one profile")
def get_profile(
    profile_id: str,
    current_user: dict = Depends(require_customer),
    svc: MeasurementsService = Depends(get_svc)
):
    profile = svc.get_profile(profile_id, str(current_user["_id"]))
    return ok(data=profile)


@router.patch("/customers/measurement-profiles/{profile_id}", summary="Update profile")
def update_profile(
    profile_id: str,
    body: MeasurementProfileUpdateRequest,
    current_user: dict = Depends(require_customer),
    svc: MeasurementsService = Depends(get_svc)
):
    profile = svc.update_profile(profile_id, str(current_user["_id"]), body)
    return ok(data=profile, message="Profile updated")


@router.delete("/customers/measurement-profiles/{profile_id}", summary="Soft-delete profile")
def delete_profile(
    profile_id: str,
    current_user: dict = Depends(require_customer),
    svc: MeasurementsService = Depends(get_svc)
):
    svc.delete_profile(profile_id, str(current_user["_id"]))
    return ok(message="Profile deleted")


@router.post("/customers/measurement-profiles/{profile_id}/set-default", summary="Set default profile")
def set_default_profile(
    profile_id: str,
    current_user: dict = Depends(require_customer),
    svc: MeasurementsService = Depends(get_svc)
):
    profile = svc.set_default_profile(profile_id, str(current_user["_id"]))
    return ok(data=profile, message="Default profile set")


@router.get("/customers/measurement-history", summary="Customer history of confirmed measurements")
def get_customer_history(
    current_user: dict = Depends(require_customer),
    svc: MeasurementsService = Depends(get_svc)
):
    history = svc.get_customer_history(str(current_user["_id"]))
    return ok(data=history)


# ── Garment Measurements ──────────────────────────────────────────────────────

@router.get("/garments/{garment_id}/measurements", summary="Get garment measurements")
def get_garment_measurements(
    garment_id: str,
    current_user: dict = Depends(get_current_user),
    svc: MeasurementsService = Depends(get_svc)
):
    meas = svc.get_garment_measurements(garment_id, current_user)
    return ok(data=meas)


@router.patch("/garments/{garment_id}/measurements", summary="Update garment measurements")
def update_measurements(
    garment_id: str,
    body: GarmentMeasurementUpdateRequest,
    current_user: dict = Depends(get_current_user),
    svc: MeasurementsService = Depends(get_svc)
):
    meas = svc.update_measurements(garment_id, current_user, body)
    return ok(data=meas, message="Measurements updated")


@router.post("/garments/{garment_id}/measurements/request-clarification", summary="Request clarification")
def request_clarification(
    garment_id: str,
    body: ClarificationRequest,
    current_user: dict = Depends(get_current_user), # Internal validation handles roles
    svc: MeasurementsService = Depends(get_svc)
):
    meas = svc.request_clarification(garment_id, body.note, current_user)
    return ok(data=meas, message="Clarification requested")


@router.post("/garments/{garment_id}/measurements/confirm", summary="Confirm measurements")
def confirm_measurements(
    garment_id: str,
    current_user: dict = Depends(get_current_user),
    svc: MeasurementsService = Depends(get_svc)
):
    meas = svc.confirm_measurements(garment_id, current_user)
    return ok(data=meas, message="Measurements confirmed")


@router.get("/garments/{garment_id}/measurements/history", summary="Get garment measurement history")
def get_history(
    garment_id: str,
    current_user: dict = Depends(get_current_user),
    svc: MeasurementsService = Depends(get_svc)
):
    history = svc.get_history(garment_id, current_user)
    return ok(data=history)
