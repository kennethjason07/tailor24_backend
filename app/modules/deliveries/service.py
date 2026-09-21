"""
TAILOR24 — Deliveries Service
OTP is hashed before storage. Raw OTP is NEVER persisted.
COD status flips to PAID only after delivery confirmation.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from bson import ObjectId
from pymongo.database import Database

from app.common.enums import DeliveryStatus
from app.common.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.common.utils import doc_to_dict, money_to_decimal128, to_object_id
from app.core.security import generate_otp, hash_otp, verify_otp

logger = logging.getLogger(__name__)


class DeliveriesService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _next_tracking_ref(self) -> str:
        result = self.db.counters.find_one_and_update(
            {"_id": "deliveries"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True,
        )
        return f"DEL-T24-{result['seq']:09d}"

    def create_delivery(
        self,
        order_id: str,
        hub_id: str,
        rider_id: str,
        cod_amount: Optional[Decimal] = None,
    ) -> dict:
        existing = self.db.deliveries.find_one({"orderId": ObjectId(order_id)})
        if existing:
            raise ConflictError(f"Delivery already exists for order {order_id}.")

        # Verify order
        order = self.db.orders.find_one({"_id": to_object_id(order_id)})
        if not order:
            raise NotFoundError(f"Order {order_id} not found.")

        otp = generate_otp(6)
        otp_hash = hash_otp(otp)
        now = datetime.now(timezone.utc)
        tracking_ref = self._next_tracking_ref()

        doc = {
            "orderId": ObjectId(order_id),
            "hubId": ObjectId(hub_id),
            "riderId": ObjectId(rider_id),
            "trackingReference": tracking_ref,
            "status": DeliveryStatus.ASSIGNED.value,
            "assignedAt": now,
            "pickedUpAt": None,
            "outForDeliveryAt": None,
            "deliveredAt": None,
            "deliveryOtpHash": otp_hash,  # NEVER store raw OTP
            "cod": {
                "required": cod_amount is not None,
                "amount": money_to_decimal128(cod_amount) if cod_amount else None,
                "status": "PENDING" if cod_amount else "NA",
                "collectedAt": None,
            },
            "failure": None,
            "createdAt": now,
            "updatedAt": now,
        }
        result = self.db.deliveries.insert_one(doc)
        doc["_id"] = result.inserted_id

        # Update order tracking reference
        self.db.orders.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"trackingReference": tracking_ref, "updatedAt": now}},
        )

        logger.info("Delivery created order=%s rider=%s ref=%s", order_id, rider_id, tracking_ref)
        response = doc_to_dict(doc)
        response["otp"] = otp  # Return OTP once — caller must transmit to customer
        return response

    def get_delivery(self, delivery_id: str) -> dict:
        doc = self.db.deliveries.find_one({"_id": to_object_id(delivery_id)})
        if not doc:
            raise NotFoundError(f"Delivery {delivery_id} not found.")
        d = doc_to_dict(doc)
        d.pop("deliveryOtpHash", None)
        return d

    def get_delivery_by_order(self, order_id: str) -> dict:
        doc = self.db.deliveries.find_one({"orderId": ObjectId(order_id)})
        if not doc:
            raise NotFoundError(f"No delivery for order {order_id}.")
        d = doc_to_dict(doc)
        d.pop("deliveryOtpHash", None)
        return d

    def update_status(self, delivery_id: str, new_status: str, rider_id: str) -> dict:
        doc = self.db.deliveries.find_one({"_id": to_object_id(delivery_id)})
        if not doc:
            raise NotFoundError(f"Delivery {delivery_id} not found.")
        if str(doc["riderId"]) != rider_id:
            raise ValidationError("Only the assigned rider can update this delivery.")

        now = datetime.now(timezone.utc)
        updates: dict = {"status": new_status, "updatedAt": now}

        if new_status == DeliveryStatus.PICKED_UP.value:
            updates["pickedUpAt"] = now
        elif new_status == DeliveryStatus.OUT_FOR_DELIVERY.value:
            updates["outForDeliveryAt"] = now

        result = self.db.deliveries.find_one_and_update(
            {"_id": to_object_id(delivery_id)},
            {"$set": updates},
            return_document=True,
        )
        d = doc_to_dict(result)
        d.pop("deliveryOtpHash", None)
        return d

    def confirm_delivery(
        self,
        delivery_id: str,
        rider_id: str,
        otp: Optional[str] = None,
        cod_collected: bool = False,
    ) -> dict:
        doc = self.db.deliveries.find_one({"_id": to_object_id(delivery_id)})
        if not doc:
            raise NotFoundError(f"Delivery {delivery_id} not found.")
        if str(doc["riderId"]) != rider_id:
            raise ValidationError("Only the assigned rider can confirm this delivery.")

        # OTP verification if hash is set
        stored_hash = doc.get("deliveryOtpHash")
        if stored_hash:
            if not otp:
                raise ValidationError("OTP is required for delivery confirmation.")
            if not verify_otp(otp, stored_hash):
                raise ValidationError("Invalid OTP.")

        now = datetime.now(timezone.utc)
        cod_updates: dict = {}

        # COD: only flip to PAID when delivery confirmed AND COD collected
        if doc["cod"]["required"] and cod_collected:
            cod_updates = {
                "cod.status": "PAID",
                "cod.collectedAt": now,
            }
            # Update order payment status
            self.db.orders.update_one(
                {"_id": doc["orderId"]},
                {"$set": {"payment.status": "PAID", "updatedAt": now}},
            )

        updates = {
            "status": DeliveryStatus.DELIVERED.value,
            "deliveredAt": now,
            "updatedAt": now,
            **cod_updates,
        }
        result = self.db.deliveries.find_one_and_update(
            {"_id": to_object_id(delivery_id)},
            {"$set": updates},
            return_document=True,
        )
        d = doc_to_dict(result)
        d.pop("deliveryOtpHash", None)
        logger.info("Delivery confirmed delivery_id=%s", delivery_id)
        return d

    def mark_failed(self, delivery_id: str, rider_id: str, reason: str) -> dict:
        doc = self.db.deliveries.find_one({"_id": to_object_id(delivery_id)})
        if not doc:
            raise NotFoundError(f"Delivery {delivery_id} not found.")
        if str(doc["riderId"]) != rider_id:
            raise ValidationError("Only the assigned rider can mark this delivery as failed.")

        now = datetime.now(timezone.utc)
        result = self.db.deliveries.find_one_and_update(
            {"_id": to_object_id(delivery_id)},
            {"$set": {
                "status": DeliveryStatus.FAILED.value,
                "failure": {"reason": reason, "failedAt": now},
                "updatedAt": now,
            }},
            return_document=True,
        )
        d = doc_to_dict(result)
        d.pop("deliveryOtpHash", None)
        return d

    def list_rider_deliveries(self, rider_id: str, status: Optional[str] = None) -> list:
        query: dict = {"riderId": ObjectId(rider_id)}
        if status:
            query["status"] = status
        docs = list(self.db.deliveries.find(query).sort("assignedAt", -1))
        result = []
        for d in docs:
            dd = doc_to_dict(d)
            dd.pop("deliveryOtpHash", None)
            result.append(dd)
        return result
