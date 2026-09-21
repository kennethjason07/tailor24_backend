"""Leave requests router."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, Query

from app.common.enums import LeaveStatus
from app.common.exceptions import NotFoundError, ValidationError
from app.common.responses import ok
from app.common.utils import doc_to_dict, to_object_id
from app.core.database import get_db
from app.core.dependencies import require_hub_manager, require_tailor, get_current_user
from app.modules.tailors.leave_schemas import LeaveRequestCreate, LeaveReviewRequest

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", summary="Apply for leave")
def apply_leave(
    body: LeaveRequestCreate,
    current_user: dict = Depends(require_tailor),
):
    db = get_db()
    tailor_profile = db.tailor_profiles.find_one({"userId": ObjectId(str(current_user["_id"]))})
    hub_id = tailor_profile["hubId"] if tailor_profile else None

    now = datetime.now(timezone.utc)
    doc = {
        "tailorId": ObjectId(str(current_user["_id"])),
        "hubId": hub_id,
        "fromDate": body.fromDate.isoformat(),
        "toDate": body.toDate.isoformat(),
        "reason": body.reason,
        "status": LeaveStatus.PENDING.value,
        "reviewedBy": None,
        "reviewedAt": None,
        "createdAt": now,
        "updatedAt": now,
    }
    db_result = db.leave_requests.insert_one(doc)
    doc["_id"] = db_result.inserted_id
    return ok(data=doc_to_dict(doc), message="Leave request submitted")


@router.get("", summary="List leave requests")
def list_leave_requests(
    status: str = Query(None),
    current_user: dict = Depends(get_current_user),
):
    db = get_db()
    query: dict = {}
    role = current_user.get("role")
    if role == "TAILOR":
        query["tailorId"] = ObjectId(str(current_user["_id"]))
    elif role in ("HUB_MANAGER", "HUB_STAFF"):
        tailor_profile = db.tailor_profiles.find_one({"userId": ObjectId(str(current_user["_id"]))})
        if tailor_profile:
            query["hubId"] = tailor_profile["hubId"]
    if status:
        query["status"] = status
    docs = list(db.leave_requests.find(query))
    return ok(data=[doc_to_dict(d) for d in docs])


@router.patch("/{request_id}/review", summary="Approve or reject leave (hub manager)")
def review_leave(
    request_id: str,
    body: LeaveReviewRequest,
    current_user: dict = Depends(require_hub_manager),
):
    if body.status == LeaveStatus.PENDING:
        raise ValidationError("Cannot set status back to PENDING.")
    db = get_db()
    doc = db.leave_requests.find_one({"_id": to_object_id(request_id)})
    if not doc:
        raise NotFoundError(f"Leave request {request_id} not found.")

    now = datetime.now(timezone.utc)
    updates = {
        "status": body.status.value,
        "reviewedBy": ObjectId(str(current_user["_id"])),
        "reviewedAt": now,
        "updatedAt": now,
    }
    result = db.leave_requests.find_one_and_update(
        {"_id": to_object_id(request_id)},
        {"$set": updates},
        return_document=True,
    )
    # If approved, update tailor availability
    if body.status == LeaveStatus.APPROVED:
        db.tailor_profiles.update_one(
            {"userId": doc["tailorId"]},
            {"$set": {"availability": "ON_LEAVE", "updatedAt": now}},
        )
    return ok(data=doc_to_dict(result), message=f"Leave {body.status.value.lower()}")
