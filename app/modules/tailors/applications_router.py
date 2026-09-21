"""Tailor applications router."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, Query

from app.common.enums import ApplicationStatus
from app.common.exceptions import ConflictError, NotFoundError
from app.common.responses import ok
from app.common.utils import doc_to_dict, to_object_id
from app.core.database import get_db
from app.core.dependencies import require_hub_manager, require_tailor
from app.modules.tailors.application_schemas import (
    ApplicationReviewRequest,
    TailorApplicationRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", summary="Submit tailor application")
def submit_application(
    body: TailorApplicationRequest,
    current_user: dict = Depends(require_tailor),
):
    db = get_db()
    user_id = str(current_user["_id"])

    existing = db.tailor_applications.find_one(
        {"tailorId": ObjectId(user_id), "status": ApplicationStatus.PENDING.value}
    )
    if existing:
        raise ConflictError("You already have a pending application.")

    # Generate application number
    count = db.tailor_applications.count_documents({})
    app_number = f"APP-T24-{count + 1:06d}"

    now = datetime.now(timezone.utc)
    doc = {
        "applicationNumber": app_number,
        "tailorId": ObjectId(user_id),
        "tailorName": current_user["name"],
        "tailorPhone": current_user["phone"],
        "hubId": to_object_id(body.hubId),
        "genderSpecialization": [g.value for g in body.genderSpecialization],
        "skills": [s.value for s in body.skills],
        "dailyCapacity": body.dailyCapacity,
        "address": body.address,
        "aadharNumber": body.aadharNumber,
        "documents": [d.model_dump() for d in body.documents],
        "notes": body.notes,
        "status": ApplicationStatus.PENDING.value,
        "reviewedBy": None,
        "reviewedAt": None,
        "reviewNotes": None,
        "signedPdfKey": None,  # set when PDF is generated
        "createdAt": now,
        "updatedAt": now,
    }
    result = db.tailor_applications.insert_one(doc)
    doc["_id"] = result.inserted_id
    return ok(data=doc_to_dict(doc), message="Application submitted")


@router.get("", summary="List applications (hub manager)")
def list_applications(
    status: str = Query(None),
    hub_id: str = Query(None),
    _: dict = Depends(require_hub_manager),
):
    db = get_db()
    query = {}
    if status:
        query["status"] = status
    if hub_id:
        query["hubId"] = ObjectId(hub_id)
    docs = list(db.tailor_applications.find(query))
    return ok(data=[doc_to_dict(d) for d in docs])


@router.get("/my", summary="My applications")
def my_applications(current_user: dict = Depends(require_tailor)):
    db = get_db()
    docs = list(db.tailor_applications.find({"tailorId": ObjectId(str(current_user["_id"]))}))
    return ok(data=[doc_to_dict(d) for d in docs])


@router.patch("/{application_id}/review", summary="Approve or reject application")
def review_application(
    application_id: str,
    body: ApplicationReviewRequest,
    current_user: dict = Depends(require_hub_manager),
):
    if body.status == ApplicationStatus.PENDING:
        from app.common.exceptions import ValidationError
        raise ValidationError("Cannot set status back to PENDING.")

    db = get_db()
    app_doc = db.tailor_applications.find_one({"_id": to_object_id(application_id)})
    if not app_doc:
        raise NotFoundError(f"Application {application_id} not found.")

    now = datetime.now(timezone.utc)
    updates = {
        "status": body.status.value,
        "reviewedBy": ObjectId(str(current_user["_id"])),
        "reviewedAt": now,
        "reviewNotes": body.notes,
        "updatedAt": now,
    }
    result = db.tailor_applications.find_one_and_update(
        {"_id": to_object_id(application_id)},
        {"$set": updates},
        return_document=True,
    )

    # If approved, create/activate tailor profile
    if body.status == ApplicationStatus.APPROVED:
        existing_profile = db.tailor_profiles.find_one({"userId": app_doc["tailorId"]})
        if not existing_profile:
            profile_doc = {
                "userId": app_doc["tailorId"],
                "hubId": app_doc["hubId"],
                "genderSpecialization": app_doc["genderSpecialization"],
                "skills": app_doc["skills"],
                "dailyCapacity": app_doc["dailyCapacity"],
                "availability": "AVAILABLE",
                "rating": 5.0,
                "ratingCount": 0,
                "assignedToday": 0,
                "leaveBalance": 12,
                "isActive": True,
                "applicationStatus": "APPROVED",
                "location": None,
                "payoutInfo": None,
                "createdAt": now,
                "updatedAt": now,
            }
            db.tailor_profiles.insert_one(profile_doc)
            # Update user role to TAILOR if needed
            db.users.update_one(
                {"_id": app_doc["tailorId"]},
                {"$set": {"role": "TAILOR", "updatedAt": now}},
            )
        logger.info("Application %s approved — tailor profile created/activated", application_id)

    return ok(data=doc_to_dict(result), message=f"Application {body.status.value.lower()}")
