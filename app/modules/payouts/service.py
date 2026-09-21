"""
TAILOR24 — Payouts Service
Two-step payout approval: Tailor → Hub Manager → Admin/Finance

CRITICAL RULES:
1. One garment creates at most ONE payout_ledger entry (unique index on garmentId).
2. Payout creation is idempotent — retries cannot create duplicates.
3. Payout CANNOT become FINANCE_PAID without the finance confirmation step.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.common.enums import PayoutClaimStatus, PayoutLedgerStatus
from app.common.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.common.utils import doc_to_dict, money_to_decimal128, to_object_id

logger = logging.getLogger(__name__)


class PayoutsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ── Ledger ────────────────────────────────────────────────────────────────

    def get_tailor_ledger(
        self,
        tailor_id: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        query: dict = {"tailorId": ObjectId(tailor_id)}
        if status:
            query["status"] = status
        docs = list(self.db.payout_ledger.find(query).sort("earnedAt", -1).skip(skip).limit(limit))
        return [doc_to_dict(d) for d in docs]

    def get_ledger_summary(self, tailor_id: str) -> dict:
        pipeline = [
            {"$match": {"tailorId": ObjectId(tailor_id)}},
            {
                "$group": {
                    "_id": "$status",
                    "total": {"$sum": {"$toDecimal": "$amount"}},
                    "count": {"$sum": 1},
                }
            },
        ]
        results = list(self.db.payout_ledger.aggregate(pipeline))
        summary: dict = {"PENDING": {"total": "0", "count": 0}, "CLAIMED": {"total": "0", "count": 0}, "PAID": {"total": "0", "count": 0}}
        for r in results:
            summary[r["_id"]] = {"total": str(r["total"]), "count": r["count"]}
        return summary

    # ── Claims ────────────────────────────────────────────────────────────────

    def _next_claim_number(self) -> str:
        result = self.db.counters.find_one_and_update(
            {"_id": "payout_claims"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True,
        )
        return f"CLM-T24-{result['seq']:06d}"

    def raise_claim(
        self,
        tailor_id: str,
        ledger_entry_ids: List[str],
        hub_id: str,
    ) -> dict:
        """Tailor raises a payout claim against PENDING ledger entries."""
        if not ledger_entry_ids:
            raise ValidationError("At least one ledger entry must be specified.")

        # Validate all entries belong to this tailor and are PENDING
        entries = list(
            self.db.payout_ledger.find(
                {
                    "_id": {"$in": [to_object_id(lid) for lid in ledger_entry_ids]},
                    "tailorId": ObjectId(tailor_id),
                    "status": PayoutLedgerStatus.PENDING.value,
                }
            )
        )
        if len(entries) != len(ledger_entry_ids):
            raise ValidationError(
                "One or more ledger entries not found, not owned by this tailor, or not in PENDING status."
            )

        total = sum(
            Decimal(str(e["amount"])) for e in entries
        )

        now = datetime.now(timezone.utc)
        claim_number = self._next_claim_number()

        claim_doc = {
            "claimNumber": claim_number,
            "tailorId": ObjectId(tailor_id),
            "hubId": ObjectId(hub_id),
            "ledgerEntryIds": [to_object_id(lid) for lid in ledger_entry_ids],
            "amount": money_to_decimal128(total),
            "status": PayoutClaimStatus.PENDING_MANAGER.value,
            "managerApproval": None,
            "financeApproval": None,
            "createdAt": now,
            "updatedAt": now,
        }
        result = self.db.payout_claims.insert_one(claim_doc)
        claim_doc["_id"] = result.inserted_id

        # Mark ledger entries as CLAIMED
        self.db.payout_ledger.update_many(
            {"_id": {"$in": [to_object_id(lid) for lid in ledger_entry_ids]}},
            {"$set": {"status": PayoutLedgerStatus.CLAIMED.value, "claimId": result.inserted_id, "updatedAt": now}},
        )
        logger.info("Claim %s raised by tailor %s amount=%s", claim_number, tailor_id, total)
        return doc_to_dict(claim_doc)

    def manager_review(
        self,
        claim_id: str,
        manager_user: dict,
        approve: bool,
        notes: Optional[str] = None,
    ) -> dict:
        claim = self.db.payout_claims.find_one({"_id": to_object_id(claim_id)})
        if not claim:
            raise NotFoundError(f"Claim {claim_id} not found.")
        if claim["status"] != PayoutClaimStatus.PENDING_MANAGER.value:
            raise BusinessRuleError(
                f"Claim is in status {claim['status']!r} — cannot review at manager step."
            )

        now = datetime.now(timezone.utc)
        new_status = (
            PayoutClaimStatus.MANAGER_APPROVED.value
            if approve
            else PayoutClaimStatus.MANAGER_REJECTED.value
        )
        updates = {
            "status": new_status,
            "managerApproval": {
                "reviewedBy": ObjectId(str(manager_user["_id"])),
                "reviewedAt": now,
                "approved": approve,
                "notes": notes,
            },
            "updatedAt": now,
        }
        # If rejected, revert ledger entries to PENDING
        if not approve:
            self.db.payout_ledger.update_many(
                {"claimId": claim["_id"]},
                {"$set": {"status": PayoutLedgerStatus.PENDING.value, "claimId": None, "updatedAt": now}},
            )
        result = self.db.payout_claims.find_one_and_update(
            {"_id": to_object_id(claim_id)},
            {"$set": updates},
            return_document=True,
        )
        logger.info("Claim %s manager_review approved=%s", claim_id, approve)
        return doc_to_dict(result)

    def finance_confirm(
        self,
        claim_id: str,
        finance_user: dict,
        transfer_reference: str,
        note: Optional[str] = None,
    ) -> dict:
        """
        Admin/Finance confirms the bank/UPI transfer.
        A claim CANNOT become PAID without this step.
        """
        claim = self.db.payout_claims.find_one({"_id": to_object_id(claim_id)})
        if not claim:
            raise NotFoundError(f"Claim {claim_id} not found.")
        if claim["status"] != PayoutClaimStatus.MANAGER_APPROVED.value:
            raise BusinessRuleError(
                f"Claim must be in MANAGER_APPROVED state before finance confirmation. "
                f"Current status: {claim['status']!r}"
            )

        now = datetime.now(timezone.utc)
        updates = {
            "status": PayoutClaimStatus.FINANCE_PAID.value,
            "financeApproval": {
                "reviewedBy": ObjectId(str(finance_user["_id"])),
                "reviewedAt": now,
                "transferReference": transfer_reference,
                "note": note,
            },
            "updatedAt": now,
        }
        result = self.db.payout_claims.find_one_and_update(
            {"_id": to_object_id(claim_id)},
            {"$set": updates},
            return_document=True,
        )
        # Mark all ledger entries as PAID
        self.db.payout_ledger.update_many(
            {"claimId": claim["_id"]},
            {
                "$set": {
                    "status": PayoutLedgerStatus.PAID.value,
                    "paidAt": now,
                    "transferReference": transfer_reference,
                    "updatedAt": now,
                }
            },
        )
        logger.info(
            "Claim %s finance_confirmed transfer_reference=%s", claim_id, transfer_reference
        )
        return doc_to_dict(result)

    def list_claims(
        self,
        tailor_id: Optional[str] = None,
        hub_id: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        query: dict = {}
        if tailor_id:
            query["tailorId"] = ObjectId(tailor_id)
        if hub_id:
            query["hubId"] = ObjectId(hub_id)
        if status:
            query["status"] = status
        docs = list(self.db.payout_claims.find(query).sort("createdAt", -1).skip(skip).limit(limit))
        return [doc_to_dict(d) for d in docs]
