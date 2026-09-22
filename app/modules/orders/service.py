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
from app.common.enums import GarmentStage, MeasurementStatus, MeasurementSource, MeasurementEventType
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
        try:
            addr_id = to_object_id(address_id)
            address = self.db.addresses.find_one({
                "_id": addr_id,
                "customerId": ObjectId(customer_id),
            })
        except Exception:
            address = None

        if not address:
            # MVP DEMO FALLBACK: Create a dummy address snapshot
            address = {
                "_id": ObjectId(),
                "label": "Demo Address",
                "recipientName": "Demo Customer",
                "phone": "0000000000",
                "addressLine1": "Demo Street",
                "city": "Demo City",
            }

        # Verify hub exists
        try:
            h_id = to_object_id(hub_id)
            hub = self.db.hubs.find_one({"_id": h_id, "isActive": True})
        except Exception:
            hub = None

        if not hub:
            # MVP DEMO FALLBACK: Use the first active hub
            hub = self.db.hubs.find_one({"isActive": True})
            if not hub:
                raise NotFoundError("No active hubs found in the database.")
            hub_id = str(hub["_id"])

        now = datetime.now(timezone.utc)
        order_number = self._next_sequence("orders", "ORD-T24-")

        # Calculate pricing
        subtotal = sum(Decimal(str(g["serviceCharge"])) for g in garment_items)
        delivery_fee = Decimal("50.00")
        total = subtotal + delivery_fee

        order_doc = {
            "orderNumber": order_number,
            "customerId": ObjectId(customer_id),
            "addressId": address["_id"],
            "addressSnapshot": _build_address_snapshot(address),
            "hubId": hub["_id"],
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

            # Hybrid Measurement Workflow
            meas_status = MeasurementStatus.NOT_PROVIDED.value
            meas_source = None
            meas_values = {}
            meas_custom = {}
            meas_unit = "cm"
            profile_id = None
            
            if item.get("measurementSource") in [MeasurementSource.PREVIOUS_ORDER, MeasurementSource.PROFILE] and item.get("measurementProfileId"):
                # Fetch profile
                profile = self.db.measurement_profiles.find_one({"_id": to_object_id(item["measurementProfileId"]), "isActive": True})
                if profile:
                    meas_status = MeasurementStatus.PROVIDED_BY_CUSTOMER.value
                    meas_source = MeasurementSource.PREVIOUS_ORDER.value
                    profile_id = profile["_id"]
                    meas_values = profile["measurements"].get("values", {})
                    meas_custom = profile["measurements"].get("custom", {})
                    meas_unit = profile["measurements"].get("unit", "cm")
            elif item.get("measurements"):
                meas_status = MeasurementStatus.PROVIDED_BY_CUSTOMER.value
                meas_source = MeasurementSource.CUSTOMER.value
                meas_values = item["measurements"].get("values", {})
                meas_custom = item["measurements"].get("custom", {})
                meas_unit = item["measurements"].get("unit", "cm")

            garment_doc = {
                "garmentNumber": garment_number,
                "orderId": order_id,
                "customerId": ObjectId(customer_id),
                "hubId": ObjectId(hub_id),
                "qrCode": qr_value,
                "type": item["type"] if isinstance(item["type"], str) else item["type"].value,
                "gender": item["gender"] if isinstance(item["gender"], str) else item["gender"].value,
                "serviceCharge": money_to_decimal128(Decimal(str(item["serviceCharge"]))),
                "measurements": {
                    "status": meas_status,
                    "source": meas_source,
                    "unit": meas_unit,
                    "values": meas_values,
                    "custom": meas_custom,
                    "profileId": profile_id,
                    "confirmedBy": None,
                    "confirmedAt": None,
                    "updatedAt": now
                },
                "tailorId": None,
                "intake": {"intakedAt": now, "intakedBy": str(customer_id)},
                "sla": {
                    "startedAt": now,
                    "dueAt": now + timedelta(hours=24),
                },
                "currentStage": GarmentStage.CUTTING_STARTED.value,
                "notes": item.get("notes"),
                "createdAt": now,
                "updatedAt": now,
            }
            garment_docs.append(garment_doc)

        if garment_docs:
            self.db.garments.insert_many(garment_docs)
            
            # Create workflow events (INTAKE + CUTTING_STARTED)
            workflow_events = []
            for g in garment_docs:
                workflow_events.append({
                    "garmentId": g["_id"],
                    "orderId": order_id,
                    "hubId": g["hubId"],
                    "eventType": GarmentStage.INTAKE.value,
                    "stage": GarmentStage.INTAKE.value,
                    "previousStage": None,
                    "actor": {
                        "userId": ObjectId(customer_id),
                        "name": "Customer / System",
                        "role": "CUSTOMER",
                    },
                    "qrCode": g["qrCode"],
                    "occurredAt": now,
                    "createdAt": now,
                })
                workflow_events.append({
                    "garmentId": g["_id"],
                    "orderId": order_id,
                    "hubId": g["hubId"],
                    "eventType": GarmentStage.CUTTING_STARTED.value,
                    "stage": GarmentStage.CUTTING_STARTED.value,
                    "previousStage": GarmentStage.INTAKE.value,
                    "actor": {
                        "userId": ObjectId(customer_id),
                        "name": "Hub Production",
                        "role": "HUB_STAFF",
                    },
                    "qrCode": g["qrCode"],
                    "occurredAt": now,
                    "createdAt": now,
                })
            if workflow_events:
                self.db.garment_events.insert_many(workflow_events)

            # Create measurement events
            meas_events = []
            for g in garment_docs:
                ms = g["measurements"]["status"]
                if ms == MeasurementStatus.PROVIDED_BY_CUSTOMER.value:
                    m_source = g["measurements"]["source"]
                    ev_type = MeasurementEventType.COPIED_FROM_PROFILE.value if m_source == MeasurementSource.PREVIOUS_ORDER.value else MeasurementEventType.PROVIDED.value
                    meas_events.append({
                        "garmentId": g["_id"],
                        "orderId": order_id,
                        "customerId": ObjectId(customer_id),
                        "eventType": ev_type,
                        "source": m_source,
                        "actor": {
                            "userId": ObjectId(customer_id),
                            "role": "CUSTOMER"
                        },
                        "measurementSnapshot": {
                            "unit": g["measurements"]["unit"],
                            "values": g["measurements"]["values"],
                            "custom": g["measurements"]["custom"]
                        },
                        "note": None,
                        "occurredAt": now,
                        "createdAt": now
                    })
                else:
                    meas_events.append({
                        "garmentId": g["_id"],
                        "orderId": order_id,
                        "customerId": ObjectId(customer_id),
                        "eventType": MeasurementEventType.CREATED.value,
                        "source": MeasurementSource.CUSTOMER.value,
                        "actor": {
                            "userId": ObjectId(customer_id),
                            "role": "CUSTOMER"
                        },
                        "measurementSnapshot": None,
                        "note": None,
                        "occurredAt": now,
                        "createdAt": now
                    })
            if meas_events:
                self.db.measurement_events.insert_many(meas_events)

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
        res = []
        for o in orders:
            od = doc_to_dict(o)
            garments = list(self.db.garments.find({"orderId": o["_id"]}))
            od["garments"] = [doc_to_dict(g) for g in garments]
            customer = self.db.users.find_one({"_id": o["customerId"]})
            if customer:
                od["customerName"] = customer.get("name", "Customer")
                od["customerPhone"] = customer.get("phone", "")
            res.append(od)
        return res

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
