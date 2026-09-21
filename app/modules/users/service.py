"""Users service."""
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


class UsersService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_user(
        self,
        name: str,
        phone: str,
        password: str,
        role: str,
        email: Optional[str] = None,
    ) -> dict:
        if self.db.users.find_one({"phone": phone}):
            raise ConflictError(f"Phone {phone!r} is already registered.")
        now = datetime.now(timezone.utc)
        doc = {
            "name": name,
            "phone": phone,
            "email": email,
            "role": role,
            "passwordHash": hash_password(password),
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
        }
        result = self.db.users.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc_to_dict(doc)

    def get_user(self, user_id: str) -> dict:
        user = self.db.users.find_one({"_id": to_object_id(user_id)})
        if not user:
            raise NotFoundError(f"User {user_id} not found.")
        d = doc_to_dict(user)
        d.pop("passwordHash", None)
        return d

    def list_users(self, role: Optional[str] = None, skip: int = 0, limit: int = 20) -> List[dict]:
        query = {}
        if role:
            query["role"] = role
        users = list(self.db.users.find(query).skip(skip).limit(limit))
        result = []
        for u in users:
            d = doc_to_dict(u)
            d.pop("passwordHash", None)
            result.append(d)
        return result

    def update_user(self, user_id: str, updates: dict) -> dict:
        updates["updatedAt"] = datetime.now(timezone.utc)
        result = self.db.users.find_one_and_update(
            {"_id": to_object_id(user_id)},
            {"$set": updates},
            return_document=True,
        )
        if not result:
            raise NotFoundError(f"User {user_id} not found.")
        d = doc_to_dict(result)
        d.pop("passwordHash", None)
        return d

    def deactivate_user(self, user_id: str) -> dict:
        return self.update_user(user_id, {"isActive": False})
