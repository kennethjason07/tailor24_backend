"""Addresses service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from bson import ObjectId
from pymongo.database import Database

from app.common.exceptions import AuthorizationError, NotFoundError
from app.common.utils import doc_to_dict, to_object_id


class AddressesService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_address(self, customer_id: str, data: dict) -> dict:
        now = datetime.now(timezone.utc)
        # If isDefault, unset others
        if data.get("isDefault"):
            self.db.addresses.update_many(
                {"customerId": ObjectId(customer_id)},
                {"$set": {"isDefault": False}},
            )
        doc = {
            **data,
            "customerId": ObjectId(customer_id),
            "createdAt": now,
            "updatedAt": now,
        }
        result = self.db.addresses.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc_to_dict(doc)

    def list_addresses(self, customer_id: str) -> List[dict]:
        docs = self.db.addresses.find({"customerId": ObjectId(customer_id)})
        return [doc_to_dict(d) for d in docs]

    def get_address(self, address_id: str, customer_id: str) -> dict:
        doc = self.db.addresses.find_one({"_id": to_object_id(address_id)})
        if not doc:
            raise NotFoundError(f"Address {address_id} not found.")
        if str(doc["customerId"]) != customer_id:
            raise AuthorizationError("Address does not belong to this customer.")
        return doc_to_dict(doc)

    def update_address(self, address_id: str, customer_id: str, updates: dict) -> dict:
        doc = self.db.addresses.find_one({"_id": to_object_id(address_id)})
        if not doc:
            raise NotFoundError(f"Address {address_id} not found.")
        if str(doc["customerId"]) != customer_id:
            raise AuthorizationError("Address does not belong to this customer.")
        if updates.get("isDefault"):
            self.db.addresses.update_many(
                {"customerId": ObjectId(customer_id)},
                {"$set": {"isDefault": False}},
            )
        updates["updatedAt"] = datetime.now(timezone.utc)
        result = self.db.addresses.find_one_and_update(
            {"_id": to_object_id(address_id)},
            {"$set": updates},
            return_document=True,
        )
        return doc_to_dict(result)

    def delete_address(self, address_id: str, customer_id: str) -> None:
        doc = self.db.addresses.find_one({"_id": to_object_id(address_id)})
        if not doc:
            raise NotFoundError(f"Address {address_id} not found.")
        if str(doc["customerId"]) != customer_id:
            raise AuthorizationError("Address does not belong to this customer.")
        self.db.addresses.delete_one({"_id": to_object_id(address_id)})
