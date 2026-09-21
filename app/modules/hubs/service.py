"""Hubs service."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.common.exceptions import ConflictError, NotFoundError
from app.common.utils import doc_to_dict, to_object_id
from app.core.security import hash_password

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

    def _populate_manager(self, hub_dict: dict) -> dict:
        mgr_id = hub_dict.get("managerUserId")
        if mgr_id:
            user = self.db.users.find_one({"_id": to_object_id(mgr_id)})
            if user:
                user_dict = doc_to_dict(user)
                user_dict.pop("passwordHash", None)
                hub_dict["manager"] = user_dict
        return hub_dict

    def get_hub(self, hub_id: str) -> dict:
        hub = self.db.hubs.find_one({"_id": to_object_id(hub_id)})
        if not hub:
            raise NotFoundError(f"Hub {hub_id} not found.")
        return self._populate_manager(doc_to_dict(hub))

    def get_hub_by_code(self, code: str) -> Optional[dict]:
        hub = self.db.hubs.find_one({"code": code})
        return self._populate_manager(doc_to_dict(hub)) if hub else None

    def list_hubs(self, active_only: bool = True) -> List[dict]:
        query = {"isActive": True} if active_only else {}
        hubs = [doc_to_dict(h) for h in self.db.hubs.find(query)]
        return [self._populate_manager(h) for h in hubs]

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

    def delete_hub(self, hub_id: str) -> bool:
        result = self.db.hubs.delete_one({"_id": to_object_id(hub_id)})
        if result.deleted_count == 0:
            raise NotFoundError(f"Hub {hub_id} not found.")
        return True

    def create_hub_manager(self, hub_id: str, data: dict) -> dict:
        hub = self.db.hubs.find_one({"_id": to_object_id(hub_id)})
        if not hub:
            raise NotFoundError(f"Hub {hub_id} not found.")

        phone = data["phone"]
        existing = self.db.users.find_one({"phone": phone})
        if existing:
            raise ConflictError(f"User with phone {phone!r} already exists.")

        now = datetime.now(timezone.utc)
        user_doc = {
            "name": data["name"],
            "phone": phone,
            "email": data.get("email"),
            "role": "HUB_MANAGER",
            "hubId": hub["_id"],
            "hubCode": hub["code"],
            "passwordHash": hash_password(data["password"]),
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
        }
        res = self.db.users.insert_one(user_doc)
        user_doc["_id"] = res.inserted_id

        # Update hub with the manager reference
        self.db.hubs.update_one(
            {"_id": hub["_id"]},
            {"$set": {"managerUserId": res.inserted_id, "updatedAt": now}}
        )

        user_ret = doc_to_dict(user_doc)
        user_ret.pop("passwordHash", None)
        return user_ret
