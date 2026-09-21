"""Tailors service — profile management."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.common.enums import TailorAvailability
from app.common.exceptions import ConflictError, NotFoundError
from app.common.utils import doc_to_dict, to_object_id

logger = logging.getLogger(__name__)


class TailorsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_profile(self, user_id: str, data: dict) -> dict:
        if self.db.tailor_profiles.find_one({"userId": ObjectId(user_id)}):
            raise ConflictError("Tailor profile already exists for this user.")
        now = datetime.now(timezone.utc)
        doc = {
            **data,
            "userId": ObjectId(user_id),
            "hubId": to_object_id(data["hubId"]),
            "availability": TailorAvailability.AVAILABLE.value,
            "rating": 5.0,
            "ratingCount": 0,
            "assignedToday": 0,
            "leaveBalance": 12,
            "isActive": True,
            "applicationStatus": "APPROVED",
            "location": data.get("location"),
            "createdAt": now,
            "updatedAt": now,
        }
        doc.pop("hubId", None)
        doc["hubId"] = to_object_id(data["hubId"])
        result = self.db.tailor_profiles.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc_to_dict(doc)

    def get_profile_by_user(self, user_id: str) -> dict:
        doc = self.db.tailor_profiles.find_one({"userId": ObjectId(user_id)})
        if not doc:
            raise NotFoundError(f"Tailor profile not found for user {user_id}.")
        return doc_to_dict(doc)

    def get_profile(self, profile_id: str) -> dict:
        doc = self.db.tailor_profiles.find_one({"_id": to_object_id(profile_id)})
        if not doc:
            raise NotFoundError(f"Tailor profile {profile_id} not found.")
        return doc_to_dict(doc)

    def list_profiles(
        self,
        hub_id: Optional[str] = None,
        availability: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        query = {}
        if hub_id:
            query["hubId"] = ObjectId(hub_id)
        if availability:
            query["availability"] = availability
        docs = self.db.tailor_profiles.find(query).skip(skip).limit(limit)
        return [doc_to_dict(d) for d in docs]

    def update_profile(self, user_id: str, updates: dict) -> dict:
        if "hubId" in updates and updates["hubId"]:
            updates["hubId"] = to_object_id(updates["hubId"])
        updates["updatedAt"] = datetime.now(timezone.utc)
        result = self.db.tailor_profiles.find_one_and_update(
            {"userId": ObjectId(user_id)},
            {"$set": updates},
            return_document=True,
        )
        if not result:
            raise NotFoundError(f"Tailor profile not found for user {user_id}.")
        return doc_to_dict(result)

    def update_availability(self, user_id: str, availability: str) -> dict:
        return self.update_profile(user_id, {"availability": availability})

    def update_location(self, user_id: str, location: dict) -> dict:
        return self.update_profile(user_id, {"location": location})
