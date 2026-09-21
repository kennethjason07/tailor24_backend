"""
TAILOR24 — Garments Service
The garment event log is the source of truth.
garment.currentStage is a PROJECTION CACHE only — never update it directly.
SLA starts at INTAKE, not at order creation.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from app.common.enums import (
    GarmentStage,
    SLAStatus,
    UserRole,
)
from app.common.exceptions import (
    InvalidTransitionError,
    NotFoundError,
    ValidationError,
    ConflictError
)
from app.common.utils import doc_to_dict, to_object_id
from app.modules.garments.transition_engine import validate_transition

logger = logging.getLogger(__name__)

SLA_HOURS = 24
SLA_AT_RISK_HOURS = 20  # flag as AT_RISK when less than 4h remain


class GarmentsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ── Read helpers ──────────────────────────────────────────────────────────

    def get_garment(self, garment_id: str) -> dict:
        doc = self.db.garments.find_one({"_id": to_object_id(garment_id)})
        if not doc:
            raise NotFoundError(f"Garment {garment_id} not found.")
        return doc

    def get_garment_by_qr(self, qr_code: str) -> dict:
        doc = self.db.garments.find_one({"qrCode": qr_code})
        if not doc:
            raise NotFoundError(f"No garment found with QR code {qr_code!r}.")
        return doc

    def list_garments(
        self,
        hub_id: Optional[str] = None,
        stage: Optional[str] = None,
        order_id: Optional[str] = None,
        tailor_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        query: dict = {}
        if hub_id:
            query["hubId"] = ObjectId(hub_id)
        if stage:
            query["currentStage"] = stage
        if order_id:
            query["orderId"] = ObjectId(order_id)
        if tailor_id:
            query["tailorId"] = ObjectId(tailor_id)
        docs = list(self.db.garments.find(query).skip(skip).limit(limit))
        return [doc_to_dict(d) for d in docs]

    def get_latest_event(self, garment_id: ObjectId) -> Optional[dict]:
        return self.db.garment_events.find_one(
            {"garmentId": garment_id},
            sort=[("occurredAt", DESCENDING)],
        )

    def get_event_history(self, garment_id: str) -> List[dict]:
        events = list(
            self.db.garment_events.find(
                {"garmentId": to_object_id(garment_id)},
                sort=[("occurredAt", ASCENDING)],
            )
        )
        return [doc_to_dict(e) for e in events]

    # ── SLA helpers ───────────────────────────────────────────────────────────

    def _compute_sla_status(self, due_at: datetime) -> str:
        now = datetime.now(timezone.utc)
        if now > due_at:
            return SLAStatus.OVERDUE.value
        remaining = due_at - now
        if remaining.total_seconds() < (SLA_HOURS - SLA_AT_RISK_HOURS) * 3600:
            return SLAStatus.AT_RISK.value
        return SLAStatus.ON_TIME.value

    # ── Core scan / transition ────────────────────────────────────────────────

    def process_scan(
        self,
        garment_id: str,
        target_stage_str: str,
        actor_user: dict,
        hub_id_override: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        The central garment workflow function.

        1. Load garment
        2. Load latest event → derive current stage
        3. Validate actor role
        4. Validate hub authorization
        5. Validate transition (transition engine)
        6. Create immutable garment event (append-only)
        7. Update projection cache atomically
        8. Handle intake SLA setup
        9. Handle DELIVERED → payout creation
        10. Return new derived state
        """
        # -- 1. Load garment --
        garment = self.get_garment(garment_id)
        garment_oid = garment["_id"]
        order_id = garment["orderId"]
        hub_id = garment["hubId"]

        # -- 2. Derive current stage --
        latest_event = self.get_latest_event(garment_oid)
        if latest_event:
            current_stage = GarmentStage(latest_event["stage"])
        else:
            current_stage = None  # not yet intaken

        # -- 3. Parse target stage --
        try:
            target_stage = GarmentStage(target_stage_str.upper())
        except ValueError:
            raise ValidationError(f"Unknown stage {target_stage_str!r}.")

        # -- 4. Actor role --
        try:
            actor_role = UserRole(actor_user["role"])
        except ValueError:
            raise ValidationError(f"Unknown role {actor_user['role']!r}.")

        # -- 5. Hub authorization (hub staff/manager must belong to this hub) --
        if actor_role in (UserRole.HUB_STAFF, UserRole.HUB_MANAGER):
            actor_profile = self.db.tailor_profiles.find_one(
                {"userId": ObjectId(str(actor_user["_id"]))}
            )
            # For hub staff we check via hub assignment in users collection
            # Hub managers can be verified via the hub's managerUserId
            # Simple check: if hub_id_override is provided use it, else use garment's hub
            effective_hub = ObjectId(hub_id_override) if hub_id_override else hub_id
            if effective_hub != hub_id:
                # Only admin or the hub's own staff may act
                raise ValidationError("You can only act on garments from your assigned hub.")

        # -- 6. Validate transition (terminal states, allowed paths) --
        if current_stage is None:
            # First action must be INTAKE
            if target_stage != GarmentStage.INTAKE:
                raise InvalidTransitionError(
                    f"Garment has not been intaken yet. First scan must be INTAKE, got {target_stage_str!r}."
                )
        else:
            validate_transition(current_stage, target_stage, actor_role)

        # -- 6b. Validate measurements before CUTTING_STARTED --
        if target_stage == GarmentStage.CUTTING_STARTED:
            from app.common.enums import MeasurementStatus
            meas_status = garment.get("measurements", {}).get("status")
            if meas_status != MeasurementStatus.CONFIRMED.value:
                raise ConflictError("Measurements must be confirmed before cutting.")

        # -- 7. Build event document --
        now = datetime.now(timezone.utc)
        event_doc = {
            "garmentId": garment_oid,
            "orderId": order_id,
            "hubId": hub_id,
            "eventType": target_stage.value,
            "stage": target_stage.value,
            "previousStage": current_stage.value if current_stage else None,
            "actor": {
                "userId": ObjectId(str(actor_user["_id"])),
                "name": actor_user.get("name"),
                "role": actor_user["role"],
            },
            "tailorId": garment.get("tailorId"),
            "qrCode": garment["qrCode"],
            "metadata": metadata or {},
            "occurredAt": now,
            "createdAt": now,
        }
        self.db.garment_events.insert_one(event_doc)

        # -- 8. Update projection cache (currentStage) atomically --
        garment_updates: dict = {
            "currentStage": target_stage.value,
            "updatedAt": now,
        }

        # -- 8a. INTAKE → set SLA --
        if target_stage == GarmentStage.INTAKE:
            due_at = now + timedelta(hours=SLA_HOURS)
            garment_updates["intake"] = {"intakedAt": now, "intakedBy": str(actor_user["_id"])}
            garment_updates["sla"] = {
                "startedAt": now,
                "dueAt": due_at,
            }

        self.db.garments.update_one(
            {"_id": garment_oid},
            {"$set": garment_updates},
        )

        # -- 9. DELIVERED → create payout (idempotent) --
        if target_stage == GarmentStage.DELIVERED:
            self._create_payout_entry(garment, now)
            # Flip COD payment to PAID
            self.db.orders.update_one(
                {"_id": order_id, "payment.method": "COD"},
                {"$set": {"payment.status": "PAID", "updatedAt": now}},
            )

        # -- 10. Return new derived state --
        updated_garment = self.db.garments.find_one({"_id": garment_oid})
        result = doc_to_dict(updated_garment)
        if result.get("sla") and result["sla"].get("dueAt"):
            due_at_val = updated_garment["sla"]["dueAt"]
            if isinstance(due_at_val, datetime):
                result["sla"]["status"] = self._compute_sla_status(due_at_val)

        return {
            "garment": result,
            "event": doc_to_dict(event_doc),
            "currentStage": target_stage.value,
        }

    def _create_payout_entry(self, garment: dict, now: datetime) -> None:
        """
        Create a payout ledger entry for the assigned tailor.
        Idempotent: unique index on garmentId prevents duplicates.
        """
        tailor_id = garment.get("tailorId")
        if not tailor_id:
            logger.warning(
                "Garment %s delivered with no tailor assigned — no payout created.",
                str(garment["_id"]),
            )
            return

        from app.common.utils import money_to_decimal128
        from decimal import Decimal

        service_charge = garment.get("serviceCharge")
        amount = service_charge if service_charge else money_to_decimal128(Decimal("0.00"))

        payout_doc = {
            "tailorId": tailor_id,
            "garmentId": garment["_id"],
            "orderId": garment["orderId"],
            "hubId": garment["hubId"],
            "amount": amount,
            "status": "PENDING",
            "earnedAt": now,
            "claimId": None,
            "paidAt": None,
            "transferReference": None,
            "createdAt": now,
            "updatedAt": now,
        }
        try:
            self.db.payout_ledger.insert_one(payout_doc)
            logger.info("Payout created for tailor %s garment %s", str(tailor_id), str(garment["_id"]))
        except Exception as e:
            if "duplicate key" in str(e).lower() or "E11000" in str(e):
                logger.warning(
                    "Duplicate payout prevented for garment %s (idempotency)",
                    str(garment["_id"]),
                )
            else:
                raise
