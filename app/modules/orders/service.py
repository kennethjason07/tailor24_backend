"""
TAILOR24 — Orders Service
Handles order creation with immutable address snapshot and per-garment documents.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from bson import Decimal128, ObjectId
from pymongo.database import Database

from app.common.exceptions import NotFoundError, ValidationError
from app.common.utils import doc_to_dict, money_to_decimal128, to_object_id
from app.modules.garments.qr_service import generate_qr_value

logger = logging.getLogger(__name__)


def _build_address_snapshot(address: dict) -> dict:
    """Create an immutable address snapshot for the order."""
    return {
        "addressId": str(address["_id"]),
        "label": address.get("label"),
        "recipientName": address.get("recipientName"),
        "phone": address.get("phone"),
        "addressLine1": address.get("addressLine1"),
        "addressLine2": address.get("addressLine2"),
        "city": address.get("city"),
        "state": address.get("state"),
        "pincode": address.get("pincode"),
        "location": address.get("location"),
    }


class OrdersService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _next_sequence(self, collection: str, prefix: str, width: int = 9) -> str:
        """Atomic counter using MongoDB findAndModify pattern."""
        result = self.db.counters.find_one_and_update(
            {"_id": collection},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True,
        )
        seq = result["seq"]
        return f"{prefix}{seq:0{width}d}"

    def create_order(
        self,
        customer_id: str,
        address_id: str,
        hub_id: str,
        pickup_slot: dict,
        payment_method: str,
        garment_items: List[dict],
    ) -> dict:
        # Verify address belongs to customer
        address = self.db.addresses.find_one({
            "_id": to_object_id(address_id),
            "customerId": ObjectId(customer_id),
        })
        if not address:
            raise NotFoundError("Address not found or does not belong to this customer.")

        # Verify hub exists
        hub = self.db.hubs.find_one({"_id": to_object_id(hub_id), "isActive": True})
        if not hub:
            raise NotFoundError(f"Hub {hub_id} not found or inactive.")

        now = datetime.now(timezone.utc)
        order_number = self._next_sequence("orders", "ORD-T24-")

        # Calculate pricing
        subtotal = sum(Decimal(str(g["serviceCharge"])) for g in garment_items)
        delivery_fee = Decimal("50.00")
        total = subtotal + delivery_fee

        order_doc = {
            "orderNumber": order_number,
            "customerId": ObjectId(customer_id),
            "addressId": to_object_id(address_id),
            "addressSnapshot": _build_address_snapshot(address),
            "hubId": ObjectId(hub_id),
            "pickupSlot": pickup_slot,
            "payment": {
                "method": payment_method,
                "status": "PENDING",
            },
            "pricing": {
                "subtotal": money_to_decimal128(subtotal),
                "deliveryFee": money_to_decimal128(delivery_fee),
                "discount": money_to_decimal128(Decimal("0.00")),
                "tax": money_to_decimal128(Decimal("0.00")),
                "total": money_to_decimal128(total),
            },
            "garmentCount": len(garment_items),
            "trackingReference": order_number,  # same as order number for simplicity
            "createdAt": now,
            "updatedAt": now,
        }
        order_result = self.db.orders.insert_one(order_doc)
        order_id = order_result.inserted_id

        # Create one garment document per physical garment
        garment_docs = []
        for idx, item in enumerate(garment_items):
            garment_number = self._next_sequence("garments", "GRM-T24-")
            qr_seq_result = self.db.counters.find_one_and_update(
                {"_id": "qr_codes"},
                {"$inc": {"seq": 1}},
                upsert=True,
                return_document=True,
            )
            qr_value = generate_qr_value(qr_seq_result["seq"])

            garment_doc = {
                "garmentNumber": garment_number,
                "orderId": order_id,
                "customerId": ObjectId(customer_id),
                "hubId": ObjectId(hub_id),
                "qrCode": qr_value,
                "type": item["type"] if isinstance(item["type"], str) else item["type"].value,
                "gender": item["gender"] if isinstance(item["gender"], str) else item["gender"].value,
                "serviceCharge": money_to_decimal128(Decimal(str(item["serviceCharge"]))),
                "measurements": item.get("measurements", {}),
                "tailorId": None,
                "intake": None,
                "sla": None,
                # currentStage is a PROJECTION CACHE derived from garment_events.
                # It is set by the event system and must never be updated independently.
                "currentStage": None,
                "notes": item.get("notes"),
                "createdAt": now,
                "updatedAt": now,
            }
            garment_docs.append(garment_doc)

        if garment_docs:
            self.db.garments.insert_many(garment_docs)

        logger.info(
            "Order created order_number=%s garments=%d customer=%s",
            order_number, len(garment_docs), customer_id,
        )

        order_doc["_id"] = order_id
        return {
            "order": doc_to_dict(order_doc),
            "garments": [doc_to_dict(g) for g in garment_docs],
        }

    def get_order(self, order_id: str, customer_id: str | None = None) -> dict:
        query: dict = {"_id": to_object_id(order_id)}
        if customer_id:
            query["customerId"] = ObjectId(customer_id)
        order = self.db.orders.find_one(query)
        if not order:
            raise NotFoundError(f"Order {order_id} not found.")
        return doc_to_dict(order)

    def list_orders(
        self,
        customer_id: str | None = None,
        hub_id: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        query: dict = {}
        if customer_id:
            query["customerId"] = ObjectId(customer_id)
        if hub_id:
            query["hubId"] = ObjectId(hub_id)
        orders = list(self.db.orders.find(query).sort("createdAt", -1).skip(skip).limit(limit))
        return [doc_to_dict(o) for o in orders]

    def get_order_tracking(self, order_id: str) -> dict:
        """Return full tracking info: order + all garments + latest stage per garment."""
        order = self.db.orders.find_one({"_id": to_object_id(order_id)})
        if not order:
            raise NotFoundError(f"Order {order_id} not found.")

        garments = list(self.db.garments.find({"orderId": ObjectId(order_id)}))
        garment_stages = []
        for g in garments:
            latest_event = self.db.garment_events.find_one(
                {"garmentId": g["_id"]},
                sort=[("occurredAt", -1)],
            )
            garment_stages.append({
                "garmentId": str(g["_id"]),
                "garmentNumber": g["garmentNumber"],
                "qrCode": g["qrCode"],
                "type": g["type"],
                "gender": g["gender"],
                "currentStage": latest_event["stage"] if latest_event else None,
                "sla": g.get("sla"),
            })

        # Overall order progress
        delivery = self.db.deliveries.find_one({"orderId": ObjectId(order_id)})

        return {
            "order": doc_to_dict(order),
            "garments": garment_stages,
            "delivery": doc_to_dict(delivery) if delivery else None,
        }
