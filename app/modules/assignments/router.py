"""Assignments router."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_hub_manager, require_tailor
from app.modules.assignments.service import AssignmentsService

router = APIRouter()


class AssignRequest(BaseModel):
    tailorProfileId: str
    assignmentType: str = "SMART"
    overrideCapacity: bool = False


class AssignWorkerRequest(BaseModel):
    workerId: str  # userId of the HUB_STAFF worker
    workerName: str = "Hub Worker"
    stage: str = "CUTTING_STARTED"  # which stage this worker is responsible for


def get_svc():
    return AssignmentsService(get_db())


@router.get("/garments/{garment_id}/suggest", summary="Smart tailor suggestions for a garment")
def suggest_tailors(
    garment_id: str,
    limit: int = Query(5, ge=1, le=20),
    _: dict = Depends(require_hub_manager),
    svc: AssignmentsService = Depends(get_svc),
):
    suggestions = svc.suggest_tailors(garment_id, limit=limit)
    return ok(data=suggestions)


@router.post("/garments/{garment_id}/assign", summary="Assign tailor to garment")
def assign_tailor(
    garment_id: str,
    body: AssignRequest,
    current_user: dict = Depends(require_hub_manager),
    svc: AssignmentsService = Depends(get_svc),
):
    assignment = svc.assign_tailor(
        garment_id=garment_id,
        tailor_profile_id=body.tailorProfileId,
        assigned_by_user=current_user,
        assignment_type=body.assignmentType,
        override_capacity=body.overrideCapacity,
    )
    return ok(data=assignment, message="Tailor assigned successfully")


@router.get("", summary="List assignments")
def list_assignments(
    tailor_id: str = Query(None),
    hub_id: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    svc: AssignmentsService = Depends(get_svc),
):
    role = current_user.get("role")
    # Tailors can only see their own assignments
    effective_tailor_id = tailor_id
    if role == "TAILOR":
        effective_tailor_id = str(current_user["_id"])

    skip = (page - 1) * page_size
    assignments = svc.list_assignments(
        tailor_id=effective_tailor_id,
        hub_id=hub_id,
        status=status,
        skip=skip,
        limit=page_size,
    )
    return ok(data=assignments)


@router.post("/garments/{garment_id}/assign-worker", summary="Assign a hub worker to a garment")
def assign_worker(
    garment_id: str,
    body: AssignWorkerRequest,
    current_user: dict = Depends(require_hub_manager),
    svc: AssignmentsService = Depends(get_svc),
):
    """Directly assign a HUB_STAFF worker (not a tailor) to a garment."""
    result = svc.assign_worker_to_garment(
        garment_id=garment_id,
        worker_user_id=body.workerId,
        worker_name=body.workerName,
        assigned_by_user=current_user,
    )
    return ok(data=result, message="Worker assigned successfully")
