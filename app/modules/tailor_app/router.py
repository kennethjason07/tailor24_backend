"""
TAILOR24 — Tailor App Router
Aggregated endpoints for the Independent Tailor BYOD mobile application.

These endpoints are tailor-only and return data scoped to the authenticated tailor.
They exist to avoid multiple serial API calls on low-bandwidth mobile connections.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Query

from app.common.responses import ok
from app.common.utils import doc_to_dict
from app.core.database import get_db
from app.core.dependencies import require_tailor

router = APIRouter()


@router.get("/dashboard", summary="Tailor home screen aggregated data")
def tailor_dashboard(current_user: dict = Depends(require_tailor)):
    """
    Single endpoint for the tailor home screen.
    Returns profile, work counts, earnings summary, and notification badge count.
    Designed to minimise round-trips on low-bandwidth mobile connections.
    """
    db = get_db()
    tailor_user_id = ObjectId(str(current_user["_id"]))
    now = datetime.now(timezone.utc)

    # -- Tailor profile --
    profile = db.tailor_profiles.find_one({"userId": tailor_user_id})
    profile_data = doc_to_dict(profile) if profile else {}

    # -- Garment work counts --
    def garment_count(stage_filter: dict) -> int:
        q = {"tailorId": tailor_user_id}
        q.update(stage_filter)
        return db.garments.count_documents(q)

    assigned_count = garment_count({"currentStage": "STITCHING_ASSIGNED"})
    in_progress_count = garment_count({"currentStage": "STITCHING_STARTED"})
    rework_count = garment_count({"currentStage": "QC_REWORK"})
    completed_today_count = 0

    # Count garments completed (STITCHING_COMPLETED) today
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    completed_today_count = db.garments.count_documents({
        "tailorId": tailor_user_id,
        "currentStage": "STITCHING_COMPLETED",
        "updatedAt": {"$gte": today_start},
    })

    # -- At-risk garments (SLA) --
    at_risk_garments = []
    active_garments = list(db.garments.find({
        "tailorId": tailor_user_id,
        "currentStage": {"$in": ["STITCHING_ASSIGNED", "STITCHING_STARTED", "QC_REWORK"]},
    }).limit(5))

    for g in active_garments:
        sla = g.get("sla", {})
        due_at = sla.get("dueAt")
        if due_at:
            if isinstance(due_at, str):
                try:
                    due_at = datetime.fromisoformat(due_at)
                except Exception:
                    due_at = None
            if due_at:
                if due_at.tzinfo is None:
                    due_at = due_at.replace(tzinfo=timezone.utc)
                remaining_hours = (due_at - now).total_seconds() / 3600
                sla_status = "OVERDUE" if remaining_hours < 0 else ("AT_RISK" if remaining_hours < 4 else "ON_TIME")
                if sla_status in ("OVERDUE", "AT_RISK"):
                    gd = doc_to_dict(g)
                    gd["slaStatus"] = sla_status
                    gd["remainingHours"] = round(remaining_hours, 1)
                    at_risk_garments.append(gd)

    # -- Earnings summary --
    pipeline = [
        {"$match": {"tailorId": tailor_user_id}},
        {"$group": {
            "_id": "$status",
            "total": {"$sum": {"$toDouble": "$amount"}},
        }}
    ]
    earnings_by_status: dict = {}
    for row in db.payout_ledger.aggregate(pipeline):
        earnings_by_status[row["_id"]] = round(row["total"], 2)

    # Today's earnings (STITCHING_COMPLETED today)
    today_pipeline = [
        {"$match": {
            "tailorId": tailor_user_id,
            "earnedAt": {"$gte": today_start},
        }},
        {"$group": {"_id": None, "total": {"$sum": {"$toDouble": "$amount"}}}},
    ]
    today_total = 0.0
    for row in db.payout_ledger.aggregate(today_pipeline):
        today_total = round(row["total"], 2)

    # -- Notification count --
    unread_notifications = db.notifications.count_documents({
        "recipientId": tailor_user_id,
        "status": {"$ne": "READ"},
    })

    # -- Leave status --
    pending_leave = db.leave_requests.find_one({
        "tailorId": tailor_user_id,
        "status": "PENDING",
    }, sort=[("createdAt", -1)])

    return ok(data={
        "profile": profile_data,
        "availability": profile_data.get("availability", "AVAILABLE"),
        "workCounts": {
            "assigned": assigned_count,
            "inProgress": in_progress_count,
            "rework": rework_count,
            "completedToday": completed_today_count,
        },
        "atRiskGarments": at_risk_garments[:3],
        "earnings": {
            "pending": earnings_by_status.get("PENDING", 0.0),
            "claimed": earnings_by_status.get("CLAIMED", 0.0),
            "paid": earnings_by_status.get("PAID", 0.0),
            "today": today_total,
        },
        "unreadNotifications": unread_notifications,
        "pendingLeaveRequest": doc_to_dict(pending_leave) if pending_leave else None,
    })
