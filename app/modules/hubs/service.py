"""Hubs service."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.common.exceptions import ConflictError, NotFoundError
from app.common.utils import doc_to_dict, to_object_id

logger = logging.getLogger(__name__)


class HubsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_hub(self, data: dict) -> dict:
        if self.db.hubs.find_one({"code": data["code"]}):
            raise ConflictError(f"Hub code {data['code']!r} already exists.")
        now = datetime.now(timezone.utc)
        doc = {**data, "isActive": True, "createdAt": now, "updatedAt": now}
        if "managerUserId" in doc and doc["managerUserId"]:
            doc["managerUserId"] = to_object_id(doc["managerUserId"])
        result = self.db.hubs.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc_to_dict(doc)

    def get_hub(self, hub_id: str) -> dict:
        hub = self.db.hubs.find_one({"_id": to_object_id(hub_id)})
        if not hub:
            raise NotFoundError(f"Hub {hub_id} not found.")
        return doc_to_dict(hub)

    def get_hub_by_code(self, code: str) -> Optional[dict]:
        hub = self.db.hubs.find_one({"code": code})
        return doc_to_dict(hub) if hub else None

    def list_hubs(self, active_only: bool = True) -> List[dict]:
        query = {"isActive": True} if active_only else {}
        return [doc_to_dict(h) for h in self.db.hubs.find(query)]

    def update_hub(self, hub_id: str, updates: dict) -> dict:
        updates["updatedAt"] = datetime.now(timezone.utc)
        if "managerUserId" in updates and updates["managerUserId"]:
            updates["managerUserId"] = to_object_id(updates["managerUserId"])
        result = self.db.hubs.find_one_and_update(
            {"_id": to_object_id(hub_id)},
            {"$set": updates},
            return_document=True,
        )
        if not result:
            raise NotFoundError(f"Hub {hub_id} not found.")
        return doc_to_dict(result)
