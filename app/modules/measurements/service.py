from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from app.common.enums import (
    MeasurementStatus,
    MeasurementSource,
    MeasurementEventType,
    GarmentStage,
    UserRole
)
from app.common.exceptions import (
    NotFoundError,
    ValidationError,
    AuthorizationError,
    InvalidTransitionError
)
from app.common.utils import to_object_id, doc_to_dict
from app.modules.measurements.schemas import (
    MeasurementProfileCreateRequest,
    MeasurementProfileUpdateRequest,
    GarmentMeasurementUpdateRequest
)

logger = logging.getLogger(__name__)

class MeasurementsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _now(self):
        return datetime.now(timezone.utc)

    # ── Measurement Profiles ──────────────────────────────────────────────────
    
    def create_profile(self, customer_id: str, data: MeasurementProfileCreateRequest) -> dict:
        doc = {
            "customerId": ObjectId(customer_id),
            "profileName": data.profileName,
            "gender": data.gender,
            "measurements": data.measurements.model_dump(),
            "isDefault": data.isDefault,
            "isActive": True,
            "createdAt": self._now(),
            "updatedAt": self._now()
        }
        
        # If this is default, unset any other defaults
        if data.isDefault:
            self.db.measurement_profiles.update_many(
                {"customerId": ObjectId(customer_id)},
                {"$set": {"isDefault": False}}
            )
            
        try:
            res = self.db.measurement_profiles.insert_one(doc)
            doc["_id"] = res.inserted_id
            return doc_to_dict(doc)
        except Exception as e:
            if "duplicate key error" in str(e).lower():
                raise ValidationError("A profile with this name already exists.")
            raise e
            
    def list_profiles(self, customer_id: str) -> List[dict]:
        cursor = self.db.measurement_profiles.find(
            {"customerId": ObjectId(customer_id), "isActive": True}
        ).sort("createdAt", DESCENDING)
        return [doc_to_dict(doc) for doc in cursor]

    def get_profile(self, profile_id: str, customer_id: str) -> dict:
        doc = self.db.measurement_profiles.find_one({
            "_id": to_object_id(profile_id),
            "customerId": ObjectId(customer_id),
            "isActive": True
        })
        if not doc:
            raise NotFoundError("Measurement profile not found.")
        return doc_to_dict(doc)

    def update_profile(self, profile_id: str, customer_id: str, data: MeasurementProfileUpdateRequest) -> dict:
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            return self.get_profile(profile_id, customer_id)
            
        if updates.get("isDefault"):
            self.db.measurement_profiles.update_many(
                {"customerId": ObjectId(customer_id)},
                {"$set": {"isDefault": False}}
            )
            
        updates["updatedAt"] = self._now()
        
        doc = self.db.measurement_profiles.find_one_and_update(
            {"_id": to_object_id(profile_id), "customerId": ObjectId(customer_id), "isActive": True},
            {"$set": updates},
            return_document=True
        )
        if not doc:
            raise NotFoundError("Measurement profile not found.")
        return doc_to_dict(doc)

    def delete_profile(self, profile_id: str, customer_id: str) -> None:
        result = self.db.measurement_profiles.update_one(
            {"_id": to_object_id(profile_id), "customerId": ObjectId(customer_id)},
            {"$set": {"isActive": False, "updatedAt": self._now()}}
        )
        if result.matched_count == 0:
            raise NotFoundError("Measurement profile not found.")

    def set_default_profile(self, profile_id: str, customer_id: str) -> dict:
        # First unset all
        self.db.measurement_profiles.update_many(
            {"customerId": ObjectId(customer_id)},
            {"$set": {"isDefault": False}}
        )
        # Then set the specific one
        doc = self.db.measurement_profiles.find_one_and_update(
            {"_id": to_object_id(profile_id), "customerId": ObjectId(customer_id), "isActive": True},
            {"$set": {"isDefault": True, "updatedAt": self._now()}},
            return_document=True
        )
        if not doc:
            raise NotFoundError("Measurement profile not found.")
        return doc_to_dict(doc)

    # ── Garment Measurements Workflow ─────────────────────────────────────────

    def _ensure_not_locked(self, garment: dict):
        # Once CUTTING_STARTED is reached, measurements are locked
        locked_stages = {
            GarmentStage.CUTTING_STARTED, GarmentStage.CUTTING_COMPLETED,
            GarmentStage.STITCHING_ASSIGNED, GarmentStage.STITCHING_STARTED, GarmentStage.STITCHING_COMPLETED,
            GarmentStage.QC_STARTED, GarmentStage.QC_PASSED, GarmentStage.QC_REWORK,
            GarmentStage.IRONING_STARTED, GarmentStage.IRONING_COMPLETED,
            GarmentStage.PACKED, GarmentStage.DISPATCHED, GarmentStage.OUT_FOR_DELIVERY,
            GarmentStage.DELIVERED, GarmentStage.DELIVERY_FAILED
        }
        if garment.get("currentStage") in [s.value for s in locked_stages]:
            raise InvalidTransitionError("Measurements are locked after cutting has started.")

    def _create_event(self, garment: dict, event_type: MeasurementEventType, source: MeasurementSource, actor_user: dict, snapshot: dict = None, note: str = None) -> None:
        event = {
            "garmentId": garment["_id"],
            "orderId": garment["orderId"],
            "customerId": garment["customerId"],
            "eventType": event_type.value,
            "source": source.value,
            "actor": {
                "userId": actor_user["_id"],
                "role": actor_user["role"]
            },
            "measurementSnapshot": snapshot,
            "note": note,
            "occurredAt": self._now(),
            "createdAt": self._now()
        }
        self.db.measurement_events.insert_one(event)

    def get_garment_measurements(self, garment_id: str, current_user: dict) -> dict:
        garment = self.db.garments.find_one({"_id": to_object_id(garment_id)})
        if not garment:
            raise NotFoundError("Garment not found.")
            
        role = current_user.get("role")
        user_id = current_user["_id"]
        
        # Access control
        if role == UserRole.CUSTOMER and garment["customerId"] != user_id:
            raise AuthorizationError("Unauthorized to view this garment's measurements.")
        if role == UserRole.TAILOR and garment.get("tailorId") != user_id:
            raise AuthorizationError("Unauthorized to view this garment's measurements.")
        # HUB staff can view all in their hub, but simplifying for MVP
        
        meas = garment.get("measurements", {})
        meas["garmentId"] = str(garment["_id"])
        return doc_to_dict(meas)

    def update_measurements(self, garment_id: str, current_user: dict, data: GarmentMeasurementUpdateRequest) -> dict:
        garment = self.db.garments.find_one({"_id": to_object_id(garment_id)})
        if not garment:
            raise NotFoundError("Garment not found.")
            
        # Access control
        role = current_user.get("role")
        if role == UserRole.CUSTOMER and garment["customerId"] != current_user["_id"]:
            raise AuthorizationError("Unauthorized.")
            
        self._ensure_not_locked(garment)
        
        now = self._now()
        source = MeasurementSource.CUSTOMER if role == UserRole.CUSTOMER else MeasurementSource.HUB_STAFF
        if role == UserRole.TAILOR: source = MeasurementSource.TAILOR
            
        new_status = MeasurementStatus.PROVIDED_BY_CUSTOMER
        
        snapshot = data.model_dump()
        updates = {
            "measurements.status": new_status.value,
            "measurements.source": source.value,
            "measurements.unit": snapshot["unit"],
            "measurements.values": snapshot["values"],
            "measurements.custom": snapshot["custom"],
            "measurements.updatedAt": now
        }
        
        # Are we resolving a clarification?
        prev_status = garment.get("measurements", {}).get("status")
        event_type = MeasurementEventType.CLARIFICATION_RESOLVED if prev_status == MeasurementStatus.CLARIFICATION_REQUIRED.value else MeasurementEventType.UPDATED

        self.db.garments.update_one({"_id": garment["_id"]}, {"$set": updates})
        self._create_event(garment, event_type, source, current_user, snapshot)
        
        return self.get_garment_measurements(garment_id, current_user)

    def request_clarification(self, garment_id: str, note: str, current_user: dict) -> dict:
        role = current_user.get("role")
        if role not in [UserRole.TAILOR, UserRole.HUB_STAFF, UserRole.HUB_MANAGER]:
            raise AuthorizationError("Unauthorized to request clarification.")
            
        garment = self.db.garments.find_one({"_id": to_object_id(garment_id)})
        if not garment:
            raise NotFoundError("Garment not found.")
            
        if role == UserRole.TAILOR and garment.get("tailorId") != current_user["_id"]:
            raise AuthorizationError("Unauthorized to request clarification for this garment.")
            
        self._ensure_not_locked(garment)
        
        now = self._now()
        self.db.garments.update_one(
            {"_id": garment["_id"]},
            {"$set": {
                "measurements.status": MeasurementStatus.CLARIFICATION_REQUIRED.value,
                "measurements.updatedAt": now
            }}
        )
        
        source = MeasurementSource.TAILOR if role == UserRole.TAILOR else MeasurementSource.HUB_STAFF
        self._create_event(garment, MeasurementEventType.CLARIFICATION_REQUESTED, source, current_user, note=note)
        
        # Create notification
        self.db.notifications.insert_one({
            "recipientUserId": garment["customerId"],
            "title": "Measurement Clarification Required",
            "body": f"Clarification requested for garment {garment.get('garmentNumber')}: {note}",
            "type": "MEASUREMENT_CLARIFICATION",
            "metadata": {"garmentId": garment_id, "orderId": str(garment["orderId"])},
            "status": "UNREAD",
            "createdAt": now
        })
        
        return self.get_garment_measurements(garment_id, current_user)

    def confirm_measurements(self, garment_id: str, current_user: dict) -> dict:
        garment = self.db.garments.find_one({"_id": to_object_id(garment_id)})
        if not garment:
            raise NotFoundError("Garment not found.")
            
        meas = garment.get("measurements", {})
        if not meas.get("values") and not meas.get("custom"):
            raise ValidationError("Cannot confirm empty measurements.")
            
        # Access control
        role = current_user.get("role")
        if role == UserRole.CUSTOMER and garment["customerId"] != current_user["_id"]:
            raise AuthorizationError("Unauthorized.")
        if role == UserRole.TAILOR and garment.get("tailorId") != current_user["_id"]:
            raise AuthorizationError("Unauthorized.")
            
        self._ensure_not_locked(garment)
        
        now = self._now()
        self.db.garments.update_one(
            {"_id": garment["_id"]},
            {"$set": {
                "measurements.status": MeasurementStatus.CONFIRMED.value,
                "measurements.confirmedBy": current_user["_id"],
                "measurements.confirmedAt": now,
                "measurements.updatedAt": now
            }}
        )
        
        source = MeasurementSource.CUSTOMER if role == UserRole.CUSTOMER else MeasurementSource.HUB_STAFF
        if role == UserRole.TAILOR: source = MeasurementSource.TAILOR
            
        snapshot = {
            "unit": meas.get("unit"),
            "values": meas.get("values"),
            "custom": meas.get("custom")
        }
        
        self._create_event(garment, MeasurementEventType.CONFIRMED, source, current_user, snapshot)
        
        return self.get_garment_measurements(garment_id, current_user)

    def get_history(self, garment_id: str, current_user: dict) -> List[dict]:
        garment = self.db.garments.find_one({"_id": to_object_id(garment_id)})
        if not garment:
            raise NotFoundError("Garment not found.")
            
        role = current_user.get("role")
        if role == UserRole.CUSTOMER and garment["customerId"] != current_user["_id"]:
            raise AuthorizationError("Unauthorized.")
            
        cursor = self.db.measurement_events.find(
            {"garmentId": garment["_id"]}
        ).sort("occurredAt", ASCENDING)
        
        return [doc_to_dict(doc) for doc in cursor]
        
    def get_customer_history(self, customer_id: str) -> List[dict]:
        # Allow customer to find past measurements
        cursor = self.db.measurement_events.find(
            {"customerId": ObjectId(customer_id), "eventType": MeasurementEventType.CONFIRMED.value}
        ).sort("occurredAt", DESCENDING)
        
        return [doc_to_dict(doc) for doc in cursor]
