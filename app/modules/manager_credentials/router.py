"""FastAPI router for Hub Manager Credential Management."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import require_hub_manager
from app.modules.manager_credentials.schemas import (
    CreateRiderRequest,
    CreateWorkerRequest,
    CreateTailorAccountRequest,
    CreateTailorDirectRequest,
)

from app.modules.manager_credentials.service import ManagerCredentialsService

router = APIRouter()


def get_svc() -> ManagerCredentialsService:
    return ManagerCredentialsService(get_db())


# ── RIDERS ──────────────────────────────────────────────────────────────────

@router.post("/riders", summary="Create delivery rider account for manager's hub")
def create_rider(
    body: CreateRiderRequest,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    data = svc.create_rider(
        manager=current_user,
        name=body.name,
        phone=body.phone,
        email=str(body.email) if body.email else None,
        password=body.password,
        emergency_contact=body.emergencyContact,
        address=body.address,
    )
    return ok(data=data, message="Delivery rider created successfully")


@router.get("/riders", summary="List delivery riders assigned to manager's hub")
def list_riders(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    account_status: Optional[str] = Query(None),
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    riders = svc.list_riders(
        manager=current_user,
        search=search,
        status=status,
        account_status=account_status,
    )
    return ok(data=riders)


@router.get("/riders/{id}", summary="Get delivery rider details")
def get_rider(
    id: str,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    rider = svc.get_user_detail(manager=current_user, user_id=id, expected_role="RIDER")
    return ok(data=rider)


@router.patch("/riders/{id}", summary="Update delivery rider details")
def update_rider(
    id: str,
    body: dict,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    # Verify manager access first
    svc.get_user_detail(manager=current_user, user_id=id, expected_role="RIDER")
    # Update fields
    db = get_db()
    db.users.update_one({"_id": id}, {"$set": body})
    updated = svc.get_user_detail(manager=current_user, user_id=id, expected_role="RIDER")
    return ok(data=updated, message="Rider details updated")


@router.post("/riders/{id}/reset-access", summary="Reset rider credentials / issue new activation token")
def reset_rider_access(
    id: str,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    res = svc.reset_access(manager=current_user, user_id=id)
    return ok(data=res, message="Rider access reset successfully")


@router.post("/riders/{id}/deactivate", summary="Deactivate rider account")
def deactivate_rider(
    id: str,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    res = svc.deactivate_user(manager=current_user, user_id=id)
    return ok(data=res, message="Rider account deactivated")


@router.post("/riders/{id}/reactivate", summary="Reactivate rider account")
def reactivate_rider(
    id: str,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    res = svc.reactivate_user(manager=current_user, user_id=id)
    return ok(data=res, message="Rider account reactivated")


# ── HUB WORKERS ─────────────────────────────────────────────────────────────

@router.post("/workers", summary="Create hub worker account")
def create_worker(
    body: CreateWorkerRequest,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    data = svc.create_worker(
        manager=current_user,
        name=body.name,
        phone=body.phone,
        email=str(body.email) if body.email else None,
        password=body.password,
        role=body.role,
    )
    return ok(data=data, message="Hub worker created successfully")



@router.get("/workers", summary="List hub workers assigned to manager's hub")
def list_workers(
    search: Optional[str] = Query(None),
    account_status: Optional[str] = Query(None),
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    workers = svc.list_workers(
        manager=current_user,
        search=search,
        account_status=account_status,
    )
    return ok(data=workers)


@router.get("/workers/{id}", summary="Get hub worker details")
def get_worker(
    id: str,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    worker = svc.get_user_detail(manager=current_user, user_id=id, expected_role="HUB_STAFF")
    return ok(data=worker)


@router.patch("/workers/{id}", summary="Update hub worker details")
def update_worker(
    id: str,
    body: dict,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    svc.get_user_detail(manager=current_user, user_id=id, expected_role="HUB_STAFF")
    db = get_db()
    db.users.update_one({"_id": id}, {"$set": body})
    updated = svc.get_user_detail(manager=current_user, user_id=id, expected_role="HUB_STAFF")
    return ok(data=updated, message="Worker details updated")


@router.post("/workers/{id}/reset-access", summary="Reset worker credentials")
def reset_worker_access(
    id: str,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    res = svc.reset_access(manager=current_user, user_id=id)
    return ok(data=res, message="Worker access reset successfully")


@router.post("/workers/{id}/deactivate", summary="Deactivate worker account")
def deactivate_worker(
    id: str,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    res = svc.deactivate_user(manager=current_user, user_id=id)
    return ok(data=res, message="Worker account deactivated")


@router.post("/workers/{id}/reactivate", summary="Reactivate worker account")
def reactivate_worker(
    id: str,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    res = svc.reactivate_user(manager=current_user, user_id=id)
    return ok(data=res, message="Worker account reactivated")


# ── INDEPENDENT TAILORS ─────────────────────────────────────────────────────

@router.post("/tailors", summary="Create independent tailor account for manager's hub")
def create_tailor_direct(
    body: CreateTailorDirectRequest,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    data = svc.create_tailor_direct(
        manager=current_user,
        name=body.name,
        phone=body.phone,
        email=str(body.email) if body.email else None,
        password=body.password,
        skills=body.skills,
        gender_specialization=body.genderSpecialization,
    )
    return ok(data=data, message="Independent tailor account created successfully")


@router.get("/tailors", summary="List tailors & tailor applications for manager's hub")
def list_tailors(
    search: Optional[str] = Query(None),
    tab: Optional[str] = Query(None),
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    data = svc.list_tailors(manager=current_user, search=search, tab=tab)
    return ok(data=data)



@router.get("/tailors/{id}", summary="Get tailor profile details")
def get_tailor(
    id: str,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    tailor = svc.get_user_detail(manager=current_user, user_id=id, expected_role="TAILOR")
    return ok(data=tailor)


@router.post("/tailors/{id}/create-account", summary="Create tailor account from approved application ID")
def create_tailor_account(
    id: str,
    body: Optional[CreateTailorAccountRequest] = None,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    pwd = body.password if body else None
    data = svc.create_tailor_account_from_application(manager=current_user, application_id=id, password=pwd)
    return ok(data=data, message="Tailor account created successfully from application")



@router.post("/tailors/{id}/reset-access", summary="Reset tailor credentials")
def reset_tailor_access(
    id: str,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    res = svc.reset_access(manager=current_user, user_id=id)
    return ok(data=res, message="Tailor access reset successfully")


@router.post("/tailors/{id}/deactivate", summary="Deactivate tailor account")
def deactivate_tailor(
    id: str,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    res = svc.deactivate_user(manager=current_user, user_id=id)
    return ok(data=res, message="Tailor account deactivated")


@router.post("/tailors/{id}/reactivate", summary="Reactivate tailor account")
def reactivate_tailor(
    id: str,
    current_user: dict = Depends(require_hub_manager),
    svc: ManagerCredentialsService = Depends(get_svc),
):
    res = svc.reactivate_user(manager=current_user, user_id=id)
    return ok(data=res, message="Tailor account reactivated")
