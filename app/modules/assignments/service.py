"""
TAILOR24 — Smart Tailor Assignment Service

Scoring algorithm (weights configurable via settings):
  Gender match        → +SCORE_WEIGHT_GENDER   (default 40)
  Skill overlap       → +SCORE_WEIGHT_SKILL    (default 25)
  Capacity headroom   → +SCORE_WEIGHT_CAPACITY (default 10, proportional)
  Rating              → tie-breaker (added as fractional)

Rules:
  - Never assign ON_LEAVE tailors
  - Never assign beyond dailyCapacity unless explicit override
  - scoreBreakdown is always returned for transparency
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.common.enums import AssignmentStatus, AssignmentType, TailorAvailability
from app.common.exceptions import (
    CapacityExceededError,
    NotFoundError,
    TailorUnavailableError,
    ValidationError,
)
from app.common.utils import doc_to_dict, to_object_id
from app.core.config import settings

logger = logging.getLogger(__name__)


def _compute_score(
    tailor_profile: dict,
    garment_type: str,
    garment_gender: str,
) -> tuple[float, dict]:
    """
    Return (total_score, score_breakdown).
    Weights are read from settings for configurability.
    """
    breakdown: dict = {}
    score: float = 0.0

    # Gender match
    gender_specs = tailor_profile.get("genderSpecialization", [])
    gender_score = 0
    if garment_gender in gender_specs or "UNISEX" in gender_specs:
        gender_score = settings.SCORE_WEIGHT_GENDER
    breakdown["genderMatch"] = gender_score
    score += gender_score

    # Skill overlap
    skills = tailor_profile.get("skills", [])
    skill_score = settings.SCORE_WEIGHT_SKILL if garment_type in skills else 0
    breakdown["skillMatch"] = skill_score
    score += skill_score

    # Capacity headroom (proportional)
    daily_cap = tailor_profile.get("dailyCapacity", 1)
    assigned_today = tailor_profile.get("assignedToday", 0)
    headroom = max(0, daily_cap - assigned_today)
    headroom_ratio = headroom / daily_cap if daily_cap > 0 else 0
    capacity_score = round(headroom_ratio * settings.SCORE_WEIGHT_CAPACITY, 2)
    breakdown["capacityHeadroom"] = capacity_score
    score += capacity_score

    # Rating as fractional tie-breaker
    rating = tailor_profile.get("rating", 5.0)
    breakdown["ratingTieBreaker"] = round(rating / 100, 4)
    score += breakdown["ratingTieBreaker"]

    breakdown["total"] = round(score, 4)
    return round(score, 4), breakdown


class AssignmentsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ── Smart suggestions ─────────────────────────────────────────────────────

    def suggest_tailors(
        self,
        garment_id: str,
        limit: int = 5,
    ) -> List[dict]:
        """Return scored tailor candidates for a garment."""
        garment = self.db.garments.find_one({"_id": to_object_id(garment_id)})
        if not garment:
            raise NotFoundError(f"Garment {garment_id} not found.")

        hub_id = garment["hubId"]
        garment_type = garment["type"]
        garment_gender = garment["gender"]

        # Fetch active, non-ON_LEAVE tailors at the same hub
        profiles = list(
            self.db.tailor_profiles.find(
                {
                    "hubId": hub_id,
                    "isActive": True,
                    "availability": {"$ne": TailorAvailability.ON_LEAVE.value},
                }
            )
        )

        candidates = []
        for profile in profiles:
            avail = profile.get("availability")
            if avail == TailorAvailability.ON_LEAVE.value:
                continue

            score, breakdown = _compute_score(profile, garment_type, garment_gender)

            # Fetch tailor user info
            user = self.db.users.find_one({"_id": profile["userId"]})
            candidates.append(
                {
                    "tailorId": str(profile["_id"]),
                    "userId": str(profile["userId"]),
                    "name": user["name"] if user else "Unknown",
                    "score": score,
                    "scoreBreakdown": breakdown,
                    "capacity": {
                        "daily": profile.get("dailyCapacity"),
                        "assignedToday": profile.get("assignedToday", 0),
                        "headroom": max(0, profile.get("dailyCapacity", 0) - profile.get("assignedToday", 0)),
                    },
                    "availability": avail,
                    "skills": profile.get("skills", []),
                    "genderSpecialization": profile.get("genderSpecialization", []),
                    "rating": profile.get("rating", 5.0),
                }
            )

        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[:limit]

    # ── Assign ────────────────────────────────────────────────────────────────

    def assign_tailor(
        self,
        garment_id: str,
        tailor_profile_id: str,
        assigned_by_user: dict,
        assignment_type: str = AssignmentType.SMART.value,
        override_capacity: bool = False,
    ) -> dict:
        """Assign a tailor to a garment and record the assignment."""
        garment = self.db.garments.find_one({"_id": to_object_id(garment_id)})
        if not garment:
            raise NotFoundError(f"Garment {garment_id} not found.")

        profile = self.db.tailor_profiles.find_one({"_id": to_object_id(tailor_profile_id)})
        if not profile:
            raise NotFoundError(f"Tailor profile {tailor_profile_id} not found.")

        # Guard: ON_LEAVE check
        if profile.get("availability") == TailorAvailability.ON_LEAVE.value:
            raise TailorUnavailableError(
                f"Tailor is ON_LEAVE and cannot be assigned."
            )

        # Guard: capacity check
        daily_cap = profile.get("dailyCapacity", 0)
        assigned_today = profile.get("assignedToday", 0)
        if assigned_today >= daily_cap and not override_capacity:
            raise CapacityExceededError(
                f"Tailor has reached daily capacity ({assigned_today}/{daily_cap}). "
                "Pass override_capacity=true to force assignment."
            )

        # Compute score for transparency
        score, breakdown = _compute_score(
            profile,
            garment["type"],
            garment["gender"],
        )

        now = datetime.now(timezone.utc)

        # Cancel any existing active assignment for this garment
        self.db.tailor_assignments.update_many(
            {"garmentId": garment["_id"], "status": AssignmentStatus.ACTIVE.value},
            {"$set": {"status": AssignmentStatus.REASSIGNED.value, "updatedAt": now}},
        )

        # Create assignment record
        assignment_doc = {
            "garmentId": garment["_id"],
            "orderId": garment["orderId"],
            "hubId": garment["hubId"],
            "tailorId": profile["userId"],
            "tailorProfileId": profile["_id"],
            "assignedBy": ObjectId(str(assigned_by_user["_id"])),
            "assignmentType": assignment_type,
            "score": score,
            "scoreBreakdown": breakdown,
            "status": AssignmentStatus.ACTIVE.value,
            "assignedAt": now,
            "completedAt": None,
            "createdAt": now,
            "updatedAt": now,
        }
        self.db.tailor_assignments.insert_one(assignment_doc)

        # Update garment with assigned tailor
        self.db.garments.update_one(
            {"_id": garment["_id"]},
            {"$set": {"tailorId": profile["userId"], "updatedAt": now}},
        )

        # Increment tailor's assignedToday counter (materialized, not authoritative)
        self.db.tailor_profiles.update_one(
            {"_id": profile["_id"]},
            {"$inc": {"assignedToday": 1}, "$set": {"updatedAt": now}},
        )

        logger.info(
            "Garment %s assigned to tailor %s (type=%s score=%.2f)",
            garment_id, str(profile["userId"]), assignment_type, score,
        )
        return doc_to_dict(assignment_doc)

    def list_assignments(
        self,
        tailor_id: Optional[str] = None,
        garment_id: Optional[str] = None,
        hub_id: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        query: dict = {}
        if tailor_id:
            query["tailorId"] = ObjectId(tailor_id)
        if garment_id:
            query["garmentId"] = ObjectId(garment_id)
        if hub_id:
            query["hubId"] = ObjectId(hub_id)
        if status:
            query["status"] = status
        docs = list(self.db.tailor_assignments.find(query).skip(skip).limit(limit))
        return [doc_to_dict(d) for d in docs]
