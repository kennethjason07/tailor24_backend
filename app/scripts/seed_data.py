"""
TAILOR24 — Development Seed Data Script
Populates the database with representative test data for development only.

WARNING: NEVER run this in production.
All seed users are clearly marked as test/development data.
No real credentials are hardcoded.

Usage:
    python -m app.scripts.seed_data
"""
from __future__ import annotations

import logging
import sys
import os
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bson import ObjectId

from app.core.config import settings
from app.core.database import connect_to_mongo, get_db
from app.core.security import hash_password
from app.common.utils import money_to_decimal128
from app.modules.garments.qr_service import generate_qr_value
from app.scripts.init_db import init_collections, init_indexes

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

DEV_PASSWORD = "Dev@12345"  # Used for ALL seed users — change in any real environment


def seed(db) -> None:
    now = datetime.now(timezone.utc)

    # ── Guard: only run in development ────────────────────────────────────────
    if settings.is_production:
        logger.error("Seed script MUST NOT run in production! Aborting.")
        sys.exit(1)

    logger.info("Seeding development data …")

    # ── Helper: upsert user by phone ─────────────────────────────────────────
    def upsert_user(name, phone, role, email=None) -> dict:
        existing = db.users.find_one({"phone": phone})
        if existing:
            logger.info("User already exists: %s (%s)", name, phone)
            return existing
        doc = {
            "name": name,
            "phone": phone,
            "email": email,
            "role": role,
            "passwordHash": hash_password(DEV_PASSWORD),
            "isActive": True,
            "_dev": True,  # mark as seed data
            "createdAt": now,
            "updatedAt": now,
        }
        result = db.users.insert_one(doc)
        doc["_id"] = result.inserted_id
        logger.info("Created user: %s (%s) role=%s", name, phone, role)
        return doc

    # ── Users ─────────────────────────────────────────────────────────────────
    super_admin = upsert_user("Super Admin", "+910000000000", "SUPER_ADMIN", "superadmin@tailor24.dev")
    admin = upsert_user("Admin Finance", "+910000000001", "ADMIN_FINANCE", "admin@tailor24.dev")
    manager = upsert_user("Hub Manager Priya", "+910000000002", "HUB_MANAGER", "manager@tailor24.dev")
    staff = upsert_user("Hub Staff Ramu", "+910000000003", "HUB_STAFF", "staff@tailor24.dev")
    rider = upsert_user("Rider Arjun", "+910000000004", "RIDER", "rider@tailor24.dev")
    tailor1 = upsert_user("Lata Devi", "+910000000005", "TAILOR", "lata@tailor24.dev")
    tailor2 = upsert_user("Santosh Kumar", "+910000000006", "TAILOR", "santosh@tailor24.dev")
    tailor3 = upsert_user("Meera Bai", "+910000000007", "TAILOR", "meera@tailor24.dev")
    customer = upsert_user("Ravi Sharma", "+910000000008", "CUSTOMER", "ravi@example.dev")

    # ── Hub ───────────────────────────────────────────────────────────────────
    hub = db.hubs.find_one({"code": "HUB-JAIPUR-01"})
    if not hub:
        hub_doc = {
            "name": "Jaipur Main Hub",
            "code": "HUB-JAIPUR-01",
            "addressLine1": "12, Tonk Road",
            "city": "Jaipur",
            "state": "Rajasthan",
            "pincode": "302001",
            "location": {"type": "Point", "coordinates": [75.7873, 26.9124]},
            "contactPhone": "+919800000001",
            "managerUserId": manager["_id"],
            "isActive": True,
            "_dev": True,
            "createdAt": now,
            "updatedAt": now,
        }
        result = db.hubs.insert_one(hub_doc)
        hub_doc["_id"] = result.inserted_id
        hub = hub_doc
        logger.info("Created hub: Jaipur Main Hub")
    else:
        logger.info("Hub already exists: Jaipur Main Hub")

    hub_id = hub["_id"]

    # ── Tailor Profiles ───────────────────────────────────────────────────────
    def upsert_tailor_profile(user, gender_specs, skills, daily_cap):
        existing = db.tailor_profiles.find_one({"userId": user["_id"]})
        if existing:
            return existing
        doc = {
            "userId": user["_id"],
            "hubId": hub_id,
            "genderSpecialization": gender_specs,
            "skills": skills,
            "dailyCapacity": daily_cap,
            "availability": "AVAILABLE",
            "rating": 4.9,
            "ratingCount": 42,
            "assignedToday": 0,
            "leaveBalance": 12,
            "isActive": True,
            "applicationStatus": "APPROVED",
            "location": None,
            "payoutInfo": None,
            "_dev": True,
            "createdAt": now,
            "updatedAt": now,
        }
        result = db.tailor_profiles.insert_one(doc)
        doc["_id"] = result.inserted_id
        logger.info("Created tailor profile for %s", user["name"])
        return doc

    upsert_tailor_profile(tailor1, ["LADIES", "KIDS"], ["KURTA", "SAREE", "DRESS"], 50)
    upsert_tailor_profile(tailor2, ["GENTS", "UNISEX"], ["SHIRT", "TROUSER", "SUIT"], 12)
    upsert_tailor_profile(tailor3, ["LADIES", "GENTS", "KIDS"], ["SHIRT", "KURTA", "DRESS"], 20)

    # ── Customer Address ──────────────────────────────────────────────────────
    addr = db.addresses.find_one({"customerId": customer["_id"]})
    if not addr:
        addr_doc = {
            "customerId": customer["_id"],
            "label": "Home",
            "recipientName": "Ravi Sharma",
            "phone": "+910000000008",
            "addressLine1": "45, Gandhi Nagar",
            "addressLine2": "Near Shiv Temple",
            "city": "Jaipur",
            "state": "Rajasthan",
            "pincode": "302015",
            "location": {"type": "Point", "coordinates": [75.8069, 26.9005]},
            "isDefault": True,
            "_dev": True,
            "createdAt": now,
            "updatedAt": now,
        }
        result = db.addresses.insert_one(addr_doc)
        addr_doc["_id"] = result.inserted_id
        addr = addr_doc
        logger.info("Created customer address for Ravi")

    # ── Sample Order + Garments ───────────────────────────────────────────────
    order = db.orders.find_one({"customerId": customer["_id"]})
    if not order:
        # Counter
        def next_seq(name, prefix, width=9):
            res = db.counters.find_one_and_update(
                {"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=True
            )
            return f"{prefix}{res['seq']:0{width}d}"

        order_number = next_seq("orders", "ORD-T24-")
        order_doc = {
            "orderNumber": order_number,
            "customerId": customer["_id"],
            "addressId": addr["_id"],
            "addressSnapshot": {
                "recipientName": "Ravi Sharma",
                "phone": "+910000000008",
                "addressLine1": "45, Gandhi Nagar",
                "city": "Jaipur",
                "state": "Rajasthan",
                "pincode": "302015",
            },
            "hubId": hub_id,
            "pickupSlot": {"date": "2026-09-22", "startTime": "10:00", "endTime": "11:00"},
            "payment": {"method": "COD", "status": "PENDING"},
            "pricing": {
                "subtotal": money_to_decimal128(Decimal("500.00")),
                "deliveryFee": money_to_decimal128(Decimal("50.00")),
                "discount": money_to_decimal128(Decimal("0.00")),
                "tax": money_to_decimal128(Decimal("0.00")),
                "total": money_to_decimal128(Decimal("550.00")),
            },
            "garmentCount": 2,
            "trackingReference": order_number,
            "_dev": True,
            "createdAt": now,
            "updatedAt": now,
        }
        res = db.orders.insert_one(order_doc)
        order_doc["_id"] = res.inserted_id
        order = order_doc
        logger.info("Created sample order: %s", order_number)

        # Two garments
        garments_data = [
            {"type": "SHIRT", "gender": "GENTS", "charge": "250.00"},
            {"type": "KURTA", "gender": "LADIES", "charge": "250.00"},
        ]
        for g in garments_data:
            grm_num = next_seq("garments", "GRM-T24-")
            qr_res = db.counters.find_one_and_update(
                {"_id": "qr_codes"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True
            )
            qr_val = generate_qr_value(qr_res["seq"])
            garment_doc = {
                "garmentNumber": grm_num,
                "orderId": order["_id"],
                "customerId": customer["_id"],
                "hubId": hub_id,
                "qrCode": qr_val,
                "type": g["type"],
                "gender": g["gender"],
                "serviceCharge": money_to_decimal128(Decimal(g["charge"])),
                "measurements": {"unit": "cm", "standard": "M", "custom": {"chest": 40}},
                "tailorId": None,
                "intake": None,
                "sla": None,
                "currentStage": None,
                "_dev": True,
                "createdAt": now,
                "updatedAt": now,
            }
            db.garments.insert_one(garment_doc)
            logger.info("Created garment %s qr=%s", grm_num, qr_val)
    else:
        logger.info("Sample order already exists.")

    logger.info("=== Seed complete ===")
    logger.info("Login with any seed phone at POST /api/v1/auth/login")
    logger.info("Password for all seed users: %s", DEV_PASSWORD)


def main() -> None:
    logger.info("=== TAILOR24 Seed Data (DEVELOPMENT ONLY) ===")
    connect_to_mongo()
    db = get_db()
    init_collections(db)
    init_indexes(db)
    seed(db)


if __name__ == "__main__":
    main()
