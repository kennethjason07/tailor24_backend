"""Payouts router."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    require_admin_finance,
    require_hub_manager,
    require_tailor,
)
from app.modules.payouts.service import PayoutsService

router = APIRouter()


class RaiseClaimRequest(BaseModel):
    ledgerEntryIds: List[str]


class ManagerReviewRequest(BaseModel):
    approve: bool
    notes: Optional[str] = None


class FinanceConfirmRequest(BaseModel):
    transferReference: str
    note: Optional[str] = None


def get_svc():
    return PayoutsService(get_db())


@router.get("/ledger/me", summary="My payout ledger (tailor)")
def my_ledger(
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_tailor),
    svc: PayoutsService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    entries = svc.get_tailor_ledger(
        tailor_id=str(current_user["_id"]),
        status=status,
        skip=skip,
        limit=page_size,
    )
    return ok(data=entries)


@router.get("/ledger/me/summary", summary="My payout summary (tailor)")
def my_ledger_summary(
    current_user: dict = Depends(require_tailor),
    svc: PayoutsService = Depends(get_svc),
):
    summary = svc.get_ledger_summary(str(current_user["_id"]))
    return ok(data=summary)


@router.post("/claims", summary="Raise payout claim (tailor)")
def raise_claim(
    body: RaiseClaimRequest,
    current_user: dict = Depends(require_tailor),
    svc: PayoutsService = Depends(get_svc),
):
    # Fetch tailor hub
    db = get_db()
    profile = db.tailor_profiles.find_one({"userId": current_user["_id"]})
    hub_id = str(profile["hubId"]) if profile else None

    claim = svc.raise_claim(
        tailor_id=str(current_user["_id"]),
        ledger_entry_ids=body.ledgerEntryIds,
        hub_id=hub_id,
    )
    return ok(data=claim, message="Payout claim raised")


@router.get("/claims", summary="List payout claims")
def list_claims(
    hub_id: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    svc: PayoutsService = Depends(get_svc),
):
    role = current_user.get("role")
    tailor_id = None
    if role == "TAILOR":
        tailor_id = str(current_user["_id"])

    skip = (page - 1) * page_size
    claims = svc.list_claims(
        tailor_id=tailor_id,
        hub_id=hub_id,
        status=status,
        skip=skip,
        limit=page_size,
    )
    return ok(data=claims)


@router.patch("/claims/{claim_id}/manager-review", summary="Manager review claim")
def manager_review(
    claim_id: str,
    body: ManagerReviewRequest,
    current_user: dict = Depends(require_hub_manager),
    svc: PayoutsService = Depends(get_svc),
):
    claim = svc.manager_review(
        claim_id=claim_id,
        manager_user=current_user,
        approve=body.approve,
        notes=body.notes,
    )
    action = "approved" if body.approve else "rejected"
    return ok(data=claim, message=f"Claim {action} by manager")


@router.patch("/claims/{claim_id}/finance-confirm", summary="Finance confirm transfer")
def finance_confirm(
    claim_id: str,
    body: FinanceConfirmRequest,
    current_user: dict = Depends(require_admin_finance),
    svc: PayoutsService = Depends(get_svc),
):
    claim = svc.finance_confirm(
        claim_id=claim_id,
        finance_user=current_user,
        transfer_reference=body.transferReference,
        note=body.note,
    )
    return ok(data=claim, message="Payout transferred and confirmed")
