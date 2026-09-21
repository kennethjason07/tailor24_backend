"""
TAILOR24 — Database Initialization Script
Creates all collections, JSON schema validators, unique indexes, and query indexes.

SAFE TO RUN MULTIPLE TIMES:
- Uses create_collection only if the collection does not exist
- Uses create_index with the safe default (no drop/recreate of existing indexes)
- Will NOT destroy existing production data

Usage:
    python -m app.scripts.init_db
"""
from __future__ import annotations

import logging
import sys
import os

# Allow running as a script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pymongo import ASCENDING, DESCENDING, GEOSPHERE
from pymongo.errors import CollectionInvalid

from app.core.config import settings
from app.core.database import connect_to_mongo, get_db, get_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def _ensure_collection(db, name: str, validator: dict | None = None) -> None:
    """Create a collection only if it does not already exist."""
    existing = db.list_collection_names()
    if name not in existing:
        kwargs = {}
        if validator:
            kwargs["validator"] = validator
            kwargs["validationLevel"] = "moderate"  # allow future fields
            kwargs["validationAction"] = "error"
        try:
            db.create_collection(name, **kwargs)
        except Exception as e:
            if "Special options not supported" in str(e):
                db.create_collection(name)
            else:
                raise e
        logger.info("Created collection: %s", name)
    else:
        logger.info("Collection already exists: %s", name)
        # Update validator if collection exists
        if validator:
            try:
                db.command("collMod", name, validator=validator, validationLevel="moderate")
            except Exception as e:
                logger.warning("Could not update validator for %s: %s", name, e)


def _idx(db, collection: str, keys, **kwargs) -> None:
    """Create an index safely — skips if already exists."""
    try:
        db[collection].create_index(keys, **kwargs)
    except Exception as e:
        logger.warning("Index on %s skipped: %s", collection, e)


def init_collections(db) -> None:
    # ── users ─────────────────────────────────────────────────────────────────
    _ensure_collection(db, "users", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["name", "phone", "role", "isActive", "createdAt"],
            "properties": {
                "name": {"bsonType": "string"},
                "phone": {"bsonType": "string"},
                "email": {"bsonType": ["string", "null"]},
                "role": {"bsonType": "string", "enum": [
                    "CUSTOMER", "TAILOR", "HUB_STAFF", "HUB_MANAGER", "RIDER", "ADMIN_FINANCE"
                ]},
                "isActive": {"bsonType": "bool"},
                "passwordHash": {"bsonType": "string"},
            },
        }
    })

    # ── hubs ──────────────────────────────────────────────────────────────────
    _ensure_collection(db, "hubs", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["name", "code", "isActive", "createdAt"],
            "properties": {
                "name": {"bsonType": "string"},
                "code": {"bsonType": "string"},
                "isActive": {"bsonType": "bool"},
            },
        }
    })

    # ── addresses ─────────────────────────────────────────────────────────────
    _ensure_collection(db, "addresses")

    # ── tailor_profiles ───────────────────────────────────────────────────────
    _ensure_collection(db, "tailor_profiles")

    # ── tailor_applications ───────────────────────────────────────────────────
    _ensure_collection(db, "tailor_applications")

    # ── leave_requests ────────────────────────────────────────────────────────
    _ensure_collection(db, "leave_requests")

    # ── orders ────────────────────────────────────────────────────────────────
    _ensure_collection(db, "orders", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["orderNumber", "customerId", "hubId", "garmentCount", "createdAt"],
            "properties": {
                "orderNumber": {"bsonType": "string"},
                "garmentCount": {"bsonType": "int"},
            },
        }
    })

    # ── garments ──────────────────────────────────────────────────────────────
    _ensure_collection(db, "garments", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["garmentNumber", "orderId", "customerId", "hubId", "qrCode", "type", "gender", "createdAt"],
            "properties": {
                "garmentNumber": {"bsonType": "string"},
                "qrCode": {"bsonType": "string"},
                "type": {"bsonType": "string", "enum": [
                    "SHIRT", "TROUSER", "KURTA", "SUIT", "SAREE", "DRESS", "OTHER"
                ]},
                "gender": {"bsonType": "string", "enum": [
                    "LADIES", "GENTS", "KIDS", "UNISEX"
                ]},
            },
        }
    })

    # ── garment_events (append-only) ──────────────────────────────────────────
    _ensure_collection(db, "garment_events", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["garmentId", "orderId", "hubId", "eventType", "stage", "occurredAt"],
            "properties": {
                "eventType": {"bsonType": "string"},
                "stage": {"bsonType": "string"},
            },
        }
    })

    # ── tailor_assignments ────────────────────────────────────────────────────
    _ensure_collection(db, "tailor_assignments")

    # ── payout_ledger ─────────────────────────────────────────────────────────
    _ensure_collection(db, "payout_ledger", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["tailorId", "garmentId", "orderId", "hubId", "amount", "status", "createdAt"],
            "properties": {
                "status": {"bsonType": "string", "enum": [
                    "PENDING", "CLAIMED", "PAID", "DISPUTED"
                ]},
            },
        }
    })

    # ── payout_claims ─────────────────────────────────────────────────────────
    _ensure_collection(db, "payout_claims")

    # ── deliveries ────────────────────────────────────────────────────────────
    _ensure_collection(db, "deliveries")

    # ── notifications ─────────────────────────────────────────────────────────
    _ensure_collection(db, "notifications")

    # ── counters (internal sequence generator) ────────────────────────────────
    _ensure_collection(db, "counters")

    # ── auth_otps ─────────────────────────────────────────────────────────────
    _ensure_collection(db, "auth_otps")


def init_indexes(db) -> None:
    logger.info("Creating indexes …")

    # users
    _idx(db, "users", [("phone", ASCENDING)], unique=True, name="users_phone_unique")
    _idx(db, "users", [("email", ASCENDING)], unique=True, sparse=True, name="users_email_unique")
    _idx(db, "users", [("role", ASCENDING)], name="users_role")

    # hubs
    _idx(db, "hubs", [("code", ASCENDING)], unique=True, name="hubs_code_unique")
    _idx(db, "hubs", [("location", GEOSPHERE)], name="hubs_location_2dsphere", sparse=True)

    # addresses
    _idx(db, "addresses", [("customerId", ASCENDING)], name="addresses_customer")
    _idx(db, "addresses", [("location", GEOSPHERE)], name="addresses_location_2dsphere", sparse=True)

    # tailor_profiles
    _idx(db, "tailor_profiles", [("userId", ASCENDING)], unique=True, name="tailor_profiles_user_unique")
    _idx(db, "tailor_profiles", [("hubId", ASCENDING)], name="tailor_profiles_hub")
    _idx(db, "tailor_profiles", [("hubId", ASCENDING), ("availability", ASCENDING)], name="tailor_profiles_hub_avail")
    _idx(db, "tailor_profiles", [("location", GEOSPHERE)], name="tailor_profiles_location_2dsphere", sparse=True)

    # tailor_applications
    _idx(db, "tailor_applications", [("applicationNumber", ASCENDING)], unique=True, name="applications_number_unique")
    _idx(db, "tailor_applications", [("tailorId", ASCENDING), ("status", ASCENDING)], name="applications_tailor_status")

    # leave_requests
    _idx(db, "leave_requests", [("tailorId", ASCENDING)], name="leave_tailor")
    _idx(db, "leave_requests", [("hubId", ASCENDING), ("status", ASCENDING)], name="leave_hub_status")

    # orders
    _idx(db, "orders", [("orderNumber", ASCENDING)], unique=True, name="orders_number_unique")
    _idx(db, "orders", [("customerId", ASCENDING), ("createdAt", DESCENDING)], name="orders_customer_date")
    _idx(db, "orders", [("hubId", ASCENDING), ("createdAt", DESCENDING)], name="orders_hub_date")
    _idx(db, "orders", [("trackingReference", ASCENDING)], name="orders_tracking")

    # garments
    _idx(db, "garments", [("qrCode", ASCENDING)], unique=True, name="garments_qr_unique")
    _idx(db, "garments", [("garmentNumber", ASCENDING)], unique=True, name="garments_number_unique")
    _idx(db, "garments", [("orderId", ASCENDING)], name="garments_order")
    _idx(db, "garments", [("hubId", ASCENDING), ("currentStage", ASCENDING)], name="garments_hub_stage")
    _idx(db, "garments", [("tailorId", ASCENDING)], name="garments_tailor", sparse=True)
    _idx(db, "garments", [("hubId", ASCENDING), ("sla.dueAt", ASCENDING)], name="garments_hub_sla", sparse=True)

    # garment_events — the most important indexes
    _idx(db, "garment_events", [("garmentId", ASCENDING), ("occurredAt", DESCENDING)], name="gevents_garment_date")
    _idx(db, "garment_events", [("hubId", ASCENDING), ("stage", ASCENDING), ("occurredAt", ASCENDING)], name="gevents_hub_stage_date")
    _idx(db, "garment_events", [("orderId", ASCENDING), ("occurredAt", ASCENDING)], name="gevents_order_date")

    # tailor_assignments
    _idx(db, "tailor_assignments", [("garmentId", ASCENDING), ("tailorId", ASCENDING)], name="assignments_garment_tailor")
    _idx(db, "tailor_assignments", [("tailorId", ASCENDING), ("assignedAt", DESCENDING)], name="assignments_tailor_date")
    _idx(db, "tailor_assignments", [("hubId", ASCENDING), ("status", ASCENDING)], name="assignments_hub_status")

    # payout_ledger — CRITICAL: unique on garmentId prevents duplicate payouts
    _idx(db, "payout_ledger", [("garmentId", ASCENDING)], unique=True, name="payout_ledger_garment_unique")
    _idx(db, "payout_ledger", [("tailorId", ASCENDING), ("status", ASCENDING)], name="payout_ledger_tailor_status")
    _idx(db, "payout_ledger", [("claimId", ASCENDING)], name="payout_ledger_claim", sparse=True)

    # payout_claims
    _idx(db, "payout_claims", [("claimNumber", ASCENDING)], unique=True, name="claims_number_unique")
    _idx(db, "payout_claims", [("tailorId", ASCENDING), ("status", ASCENDING)], name="claims_tailor_status")
    _idx(db, "payout_claims", [("hubId", ASCENDING), ("status", ASCENDING)], name="claims_hub_status")

    # deliveries
    _idx(db, "deliveries", [("orderId", ASCENDING)], unique=True, name="deliveries_order_unique")
    _idx(db, "deliveries", [("riderId", ASCENDING), ("status", ASCENDING)], name="deliveries_rider_status")
    _idx(db, "deliveries", [("trackingReference", ASCENDING)], unique=True, name="deliveries_tracking_unique")

    # notifications
    _idx(db, "notifications", [("recipientUserId", ASCENDING), ("createdAt", DESCENDING)], name="notifications_user_date")
    _idx(db, "notifications", [("status", ASCENDING)], name="notifications_status")

    # auth_otps
    _idx(db, "auth_otps", [("createdAt", ASCENDING)], expireAfterSeconds=300, name="auth_otps_ttl")
    _idx(db, "auth_otps", [("email", ASCENDING)], name="auth_otps_email")

    logger.info("All indexes created.")


def main() -> None:
    logger.info("=== TAILOR24 Database Initialization ===")
    logger.info("Database: %s", settings.MONGODB_DATABASE)
    connect_to_mongo()
    db = get_db()
    init_collections(db)
    init_indexes(db)
    logger.info("=== Initialization complete ===")


if __name__ == "__main__":
    main()
