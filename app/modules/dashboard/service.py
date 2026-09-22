"""
TAILOR24 — Dashboard Service
All metrics are derived from transactional data via aggregation pipelines.
NO separate dashboard collection is created or maintained.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from pymongo.database import Database

logger = logging.getLogger(__name__)

# Stages considered "in production" (not yet delivered)
IN_PRODUCTION_STAGES = [
    "INTAKE",
    "CUTTING_STARTED",
    "CUTTING_COMPLETED",
    "STITCHING_ASSIGNED",
    "STITCHING_STARTED",
    "STITCHING_COMPLETED",
    "QC_STARTED",
    "QC_PASSED",
    "QC_REWORK",
    "IRONING_STARTED",
    "IRONING_COMPLETED",
    "PACKED",
    "DISPATCHED",
    "OUT_FOR_DELIVERY",
]


class DashboardService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _hub_filter(self, hub_id: Optional[str]) -> dict:
        if hub_id:
            return {"hubId": ObjectId(hub_id)}
        return {}

    def get_overview(self, hub_id: Optional[str] = None) -> dict:
        """
        Return the main dashboard metrics.
        Computed from garments, garment_events, payout_claims, deliveries.
        """
        hub_filter = self._hub_filter(hub_id)
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # ── Garments in production ─────────────────────────────────────────
        in_production = self.db.garments.count_documents(
            {**hub_filter, "currentStage": {"$in": IN_PRODUCTION_STAGES}}
        )

        # ── Garments delivered today ───────────────────────────────────────
        delivered_today = self.db.garment_events.count_documents(
            {
                **hub_filter,
                "eventType": "DELIVERED",
                "occurredAt": {"$gte": today_start},
            }
        )

        # ── SLA at-risk / overdue ─────────────────────────────────────────
        at_risk_pipeline = [
            {
                "$match": {
                    **hub_filter,
                    "currentStage": {"$in": IN_PRODUCTION_STAGES},
                    "sla.dueAt": {"$exists": True},
                }
            },
            {
                "$project": {
                    "slaStatus": {
                        "$switch": {
                            "branches": [
                                {"case": {"$lt": ["$sla.dueAt", now]}, "then": "OVERDUE"},
                                {
                                    "case": {
                                        "$lt": [
                                            "$sla.dueAt",
                                            {"$add": [now, 4 * 3600 * 1000]},
                                        ]
                                    },
                                    "then": "AT_RISK",
                                },
                            ],
                            "default": "ON_TIME",
                        }
                    }
                }
            },
            {"$group": {"_id": "$slaStatus", "count": {"$sum": 1}}},
        ]
        sla_results = list(self.db.garments.aggregate(at_risk_pipeline))
        sla_summary = {"ON_TIME": 0, "AT_RISK": 0, "OVERDUE": 0}
        for r in sla_results:
            sla_summary[r["_id"]] = r["count"]

        # ── Pending payout claims ─────────────────────────────────────────
        claims_filter: dict = {"status": "PENDING_MANAGER"}
        if hub_id:
            claims_filter["hubId"] = ObjectId(hub_id)
        pending_claims = self.db.payout_claims.count_documents(claims_filter)

        # ── COD to collect today ──────────────────────────────────────────
        cod_filter: dict = {
            "cod.required": True,
            "cod.status": "PENDING",
            "status": "OUT_FOR_DELIVERY",
        }
        if hub_id:
            cod_filter["hubId"] = ObjectId(hub_id)
        cod_today = self.db.deliveries.count_documents(cod_filter)

        # ── Tailor capacity / availability ────────────────────────────────
        tailor_avail_pipeline = [
            {"$match": {**hub_filter, "isActive": True}},
            {"$group": {"_id": "$availability", "count": {"$sum": 1}}},
        ]
        avail_results = list(self.db.tailor_profiles.aggregate(tailor_avail_pipeline))
        tailor_availability = {"AVAILABLE": 0, "BUSY": 0, "ON_LEAVE": 0}
        for r in avail_results:
            tailor_availability[r["_id"]] = r["count"]

        # ── Stage breakdown ───────────────────────────────────────────────
        stage_pipeline = [
            {"$match": {**hub_filter, "currentStage": {"$ne": None}}},
            {"$group": {"_id": "$currentStage", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        stage_breakdown = {
            r["_id"]: r["count"]
            for r in self.db.garments.aggregate(stage_pipeline)
        }

        # ── Additional operational counts ──────────────────────────────────
        awaiting_assignment = self.db.garments.count_documents(
            {**hub_filter, "currentStage": {"$in": ["CUTTING_COMPLETED", "STITCHING_ASSIGNED", "INTAKE", "CUTTING_STARTED"]}, "tailorId": None}
        )
        qc_rework = self.db.garments.count_documents({**hub_filter, "currentStage": "QC_REWORK"})
        ready_dispatch = self.db.garments.count_documents({**hub_filter, "currentStage": "PACKED"})
        pending_leave = self.db.leave_requests.count_documents({"status": "PENDING"})

        stage_count = {
            "intake": stage_breakdown.get("INTAKE", 0),
            "cutting": stage_breakdown.get("CUTTING_STARTED", 0) + stage_breakdown.get("CUTTING_COMPLETED", 0),
            "stitching": stage_breakdown.get("STITCHING_ASSIGNED", 0) + stage_breakdown.get("STITCHING_STARTED", 0) + stage_breakdown.get("STITCHING_COMPLETED", 0),
            "qc": stage_breakdown.get("QC_STARTED", 0) + stage_breakdown.get("QC_PASSED", 0) + stage_breakdown.get("QC_REWORK", 0),
            "ironing": stage_breakdown.get("IRONING_STARTED", 0) + stage_breakdown.get("IRONING_COMPLETED", 0),
            "packed": stage_breakdown.get("PACKED", 0),
            "dispatched": stage_breakdown.get("DISPATCHED", 0) + stage_breakdown.get("OUT_FOR_DELIVERY", 0),
        }

        return {
            "garments_in_production": in_production,
            "inProduction": in_production,
            "garments_delivered_today": delivered_today,
            "deliveredToday": delivered_today,
            "sla": sla_summary,
            "atRisk": sla_summary.get("AT_RISK", 0),
            "overdue": sla_summary.get("OVERDUE", 0),
            "awaitingAssignment": awaiting_assignment,
            "qcRework": qc_rework,
            "readyDispatch": ready_dispatch,
            "pendingLeave": pending_leave,
            "pending_tailor_claims": pending_claims,
            "pendingPayouts": pending_claims,
            "cod_to_collect_today": cod_today,
            "tailor_availability": tailor_availability,
            "stage_breakdown": stage_breakdown,
            "stageCount": stage_count,
            "hub_id": hub_id,
            "generated_at": now.isoformat(),
        }

    def get_tailor_capacity(self, hub_id: Optional[str] = None) -> list:
        """List all tailors with their capacity and assignment stats."""
        hub_filter = self._hub_filter(hub_id)
        pipeline = [
            {"$match": {**hub_filter, "isActive": True}},
            {
                "$lookup": {
                    "from": "users",
                    "localField": "userId",
                    "foreignField": "_id",
                    "as": "user",
                }
            },
            {"$unwind": {"path": "$user", "preserveNullAndEmpty": True}},
            {
                "$project": {
                    "tailorId": "$_id",
                    "name": "$user.name",
                    "availability": 1,
                    "dailyCapacity": 1,
                    "assignedToday": 1,
                    "headroom": {"$subtract": ["$dailyCapacity", "$assignedToday"]},
                    "rating": 1,
                    "genderSpecialization": 1,
                    "skills": 1,
                }
            },
            {"$sort": {"availability": 1, "headroom": -1}},
        ]
        return [
            {k: str(v) if hasattr(v, "__class__") and v.__class__.__name__ == "ObjectId" else v
             for k, v in doc.items()}
            for doc in self.db.tailor_profiles.aggregate(pipeline)
        ]
