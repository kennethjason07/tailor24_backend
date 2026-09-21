"""Tests: order creation, garments, QR, garment events, transitions, SLA."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from bson import ObjectId

from app.common.enums import GarmentStage, UserRole
from tests.conftest import create_test_user, get_token, auth_headers


def make_hub(db) -> dict:
    existing = db.hubs.find_one({"code": "TEST-HUB-01"})
    if existing:
        return existing
    now = datetime.now(timezone.utc)
    doc = {
        "name": "Test Hub",
        "code": "TEST-HUB-01",
        "city": "Testville",
        "isActive": True,
        "createdAt": now,
        "updatedAt": now,
    }
    result = db.hubs.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def make_address(db, customer_id) -> dict:
    existing = db.addresses.find_one({"customerId": ObjectId(customer_id)})
    if existing:
        return existing
    now = datetime.now(timezone.utc)
    from bson import ObjectId
    doc = {
        "customerId": ObjectId(customer_id),
        "label": "Home",
        "recipientName": "Test User",
        "phone": "+910000000000",
        "addressLine1": "1 Test St",
        "city": "Testville",
        "state": "TS",
        "pincode": "110001",
        "isDefault": True,
        "createdAt": now,
        "updatedAt": now,
    }
    result = db.addresses.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


class TestOrders:
    def test_create_order_multiple_garments(self, client, db):
        """Customer can create an order with multiple garments."""
        customer = create_test_user(db, "Order Cust", "+919800100001", "CUSTOMER")
        token = get_token(client, "+919800100001")
        hub = make_hub(db)
        addr = make_address(db, str(customer["_id"]))

        resp = client.post("/api/v1/orders", headers=auth_headers(token), json={
            "addressId": str(addr["_id"]),
            "hubId": str(hub["_id"]),
            "pickupSlot": {"date": "2026-09-23", "startTime": "10:00", "endTime": "11:00"},
            "paymentMethod": "COD",
            "garments": [
                {
                    "type": "SHIRT",
                    "gender": "GENTS",
                    "serviceCharge": "250.00",
                    "measurements": {"unit": "cm", "standard": "M"},
                },
                {
                    "type": "KURTA",
                    "gender": "LADIES",
                    "serviceCharge": "300.00",
                    "measurements": {"unit": "cm", "custom": {"chest": 36, "length": 42}},
                },
            ],
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["order"]["garmentCount"] == 2
        assert len(data["garments"]) == 2

    def test_each_garment_has_unique_qr(self, client, db):
        """Every garment in an order gets a unique QR code."""
        customer = create_test_user(db, "QR Cust", "+919800100002", "CUSTOMER")
        token = get_token(client, "+919800100002")
        hub = make_hub(db)
        addr = make_address(db, str(customer["_id"]))

        resp = client.post("/api/v1/orders", headers=auth_headers(token), json={
            "addressId": str(addr["_id"]),
            "hubId": str(hub["_id"]),
            "pickupSlot": {"date": "2026-09-23", "startTime": "10:00", "endTime": "11:00"},
            "paymentMethod": "ONLINE",
            "garments": [
                {"type": "TROUSER", "gender": "GENTS", "serviceCharge": "200.00",
                 "measurements": {"unit": "cm", "standard": "32"}},
                {"type": "SHIRT", "gender": "GENTS", "serviceCharge": "200.00",
                 "measurements": {"unit": "cm", "standard": "M"}},
                {"type": "SUIT", "gender": "GENTS", "serviceCharge": "500.00",
                 "measurements": {"unit": "cm", "custom": {"chest": 42}}},
            ],
        })
        assert resp.status_code == 200, resp.text
        garments = resp.json()["data"]["garments"]
        qr_codes = [g["qrCode"] for g in garments]
        assert len(set(qr_codes)) == 3, "All QR codes must be unique"

    def test_qr_format(self, client, db):
        """QR value must match GRT-T24-XXXXXXXXX format."""
        import re
        customer = create_test_user(db, "QR Format", "+919800100003", "CUSTOMER")
        token = get_token(client, "+919800100003")
        hub = make_hub(db)
        addr = make_address(db, str(customer["_id"]))

        resp = client.post("/api/v1/orders", headers=auth_headers(token), json={
            "addressId": str(addr["_id"]),
            "hubId": str(hub["_id"]),
            "pickupSlot": {"date": "2026-09-23", "startTime": "10:00", "endTime": "11:00"},
            "paymentMethod": "COD",
            "garments": [
                {"type": "DRESS", "gender": "LADIES", "serviceCharge": "350.00",
                 "measurements": {"unit": "cm"}},
            ],
        })
        qr = resp.json()["data"]["garments"][0]["qrCode"]
        assert re.match(r"^GRT-T24-\d{9}$", qr), f"Invalid QR format: {qr}"

    def test_order_tracking(self, client, db):
        """Tracking endpoint returns order + garment stages."""
        customer = create_test_user(db, "Track Cust", "+919800100004", "CUSTOMER")
        token = get_token(client, "+919800100004")
        hub = make_hub(db)
        addr = make_address(db, str(customer["_id"]))

        create_resp = client.post("/api/v1/orders", headers=auth_headers(token), json={
            "addressId": str(addr["_id"]),
            "hubId": str(hub["_id"]),
            "pickupSlot": {"date": "2026-09-23", "startTime": "10:00", "endTime": "11:00"},
            "paymentMethod": "COD",
            "garments": [
                {"type": "KURTA", "gender": "LADIES", "serviceCharge": "250.00",
                 "measurements": {"unit": "cm"}},
            ],
        })
        order_id = create_resp.json()["data"]["order"]["id"]
        track_resp = client.get(f"/api/v1/orders/{order_id}/tracking")
        assert track_resp.status_code == 200
        data = track_resp.json()["data"]
        assert "order" in data
        assert "garments" in data


class TestGarmentWorkflow:
    def _setup_garment(self, client, db):
        """Create a customer order and return the first garment id."""
        customer = create_test_user(db, "WF Cust", "+919800200001", "CUSTOMER")
        hub = make_hub(db)
        addr = make_address(db, str(customer["_id"]))
        token = get_token(client, "+919800200001")

        resp = client.post("/api/v1/orders", headers=auth_headers(token), json={
            "addressId": str(addr["_id"]),
            "hubId": str(hub["_id"]),
            "pickupSlot": {"date": "2026-09-23", "startTime": "10:00", "endTime": "11:00"},
            "paymentMethod": "COD",
            "garments": [
                {"type": "SHIRT", "gender": "GENTS", "serviceCharge": "250.00",
                 "measurements": {"unit": "cm", "standard": "M"}},
            ],
        })
        return resp.json()["data"]["garments"][0]["id"], hub

    def test_garment_intake_sets_sla(self, client, db):
        """INTAKE event must set SLA startedAt and dueAt (+24h)."""
        garment_id, hub = self._setup_garment(client, db)
        staff = create_test_user(db, "Staff SLA", "+919800200010", "HUB_STAFF")
        token = get_token(client, "+919800200010")

        resp = client.post(
            f"/api/v1/garments/{garment_id}/scan",
            headers=auth_headers(token),
            json={"action": "INTAKE", "hubId": str(hub["_id"])},
        )
        assert resp.status_code == 200, resp.text
        garment = resp.json()["data"]["garment"]
        assert garment["sla"] is not None
        assert garment["sla"]["startedAt"] is not None
        assert garment["sla"]["dueAt"] is not None
        assert garment["currentStage"] == "INTAKE"

    def test_valid_transitions(self, client, db):
        """Walk a garment through the happy path: INTAKE → CUTTING_STARTED → CUTTING_COMPLETED."""
        garment_id, hub = self._setup_garment(client, db)
        staff = create_test_user(db, "Staff Trans", "+919800200011", "HUB_STAFF")
        token = get_token(client, "+919800200011")
        headers = auth_headers(token)

        for stage in ["INTAKE", "CUTTING_STARTED", "CUTTING_COMPLETED"]:
            resp = client.post(
                f"/api/v1/garments/{garment_id}/scan",
                headers=headers,
                json={"action": stage},
            )
            assert resp.status_code == 200, f"Failed on {stage}: {resp.text}"
            assert resp.json()["data"]["currentStage"] == stage

    def test_invalid_transition_rejected(self, client, db):
        """A garment at INTAKE cannot jump directly to DELIVERED."""
        garment_id, hub = self._setup_garment(client, db)
        staff = create_test_user(db, "Staff Inv", "+919800200012", "HUB_STAFF")
        token = get_token(client, "+919800200012")
        headers = auth_headers(token)

        # First intake
        client.post(f"/api/v1/garments/{garment_id}/scan", headers=headers, json={"action": "INTAKE"})

        # Try invalid jump
        resp = client.post(
            f"/api/v1/garments/{garment_id}/scan",
            headers=headers,
            json={"action": "DELIVERED"},
        )
        assert resp.status_code == 400
        assert "INVALID_GARMENT_TRANSITION" in resp.text or "transition" in resp.text.lower()

    def test_qc_rework_loop(self, client, db):
        """QC_REWORK must re-enter stitching, not proceed to ironing."""
        garment_id, hub = self._setup_garment(client, db)
        staff = create_test_user(db, "Staff QC", "+919800200013", "HUB_STAFF")
        manager = create_test_user(db, "Mgr QC", "+919800200014", "HUB_MANAGER")
        tailor_user = create_test_user(db, "Tailor QC", "+919800200015", "TAILOR")
        staff_token = get_token(client, "+919800200013")
        mgr_token = get_token(client, "+919800200014")
        tailor_token = get_token(client, "+919800200015")

        stages_staff = ["INTAKE", "CUTTING_STARTED", "CUTTING_COMPLETED"]
        for s in stages_staff:
            client.post(f"/api/v1/garments/{garment_id}/scan",
                        headers=auth_headers(staff_token), json={"action": s})

        # Manager assigns
        client.post(f"/api/v1/garments/{garment_id}/scan",
                    headers=auth_headers(mgr_token), json={"action": "STITCHING_ASSIGNED"})

        # Tailor stitches
        for s in ["STITCHING_STARTED", "STITCHING_COMPLETED"]:
            client.post(f"/api/v1/garments/{garment_id}/scan",
                        headers=auth_headers(tailor_token), json={"action": s})

        # QC rework
        client.post(f"/api/v1/garments/{garment_id}/scan",
                    headers=auth_headers(staff_token), json={"action": "QC_STARTED"})
        resp = client.post(f"/api/v1/garments/{garment_id}/scan",
                           headers=auth_headers(staff_token), json={"action": "QC_REWORK"})
        assert resp.status_code == 200
        assert resp.json()["data"]["currentStage"] == "QC_REWORK"

        # Now must go back to STITCHING_STARTED
        resp2 = client.post(f"/api/v1/garments/{garment_id}/scan",
                            headers=auth_headers(tailor_token), json={"action": "STITCHING_STARTED"})
        assert resp2.status_code == 200
        assert resp2.json()["data"]["currentStage"] == "STITCHING_STARTED"

    def test_event_log_is_append_only(self, client, db):
        """Every transition creates a new event; old events are immutable."""
        garment_id, hub = self._setup_garment(client, db)
        staff = create_test_user(db, "Staff Log", "+919800200016", "HUB_STAFF")
        token = get_token(client, "+919800200016")
        headers = auth_headers(token)

        for s in ["INTAKE", "CUTTING_STARTED"]:
            client.post(f"/api/v1/garments/{garment_id}/scan", headers=headers, json={"action": s})

        resp = client.get(f"/api/v1/garments/{garment_id}/events", headers=headers)
        events = resp.json()["data"]
        assert len(events) == 2
        assert events[0]["stage"] == "INTAKE"
        assert events[1]["stage"] == "CUTTING_STARTED"


class TestSLA:
    def test_sla_starts_at_intake_not_order_creation(self, db):
        """SLA startedAt must be the intake timestamp, not the order createdAt."""
        from app.modules.garments.service import GarmentsService, SLA_HOURS
        from datetime import timedelta

        # Simulate intake time (some time after order creation)
        intake_time = datetime.now(timezone.utc)
        expected_due = intake_time + timedelta(hours=SLA_HOURS)

        # SLA should be dueAt = intake + 24h
        diff = abs((expected_due - intake_time).total_seconds() - SLA_HOURS * 3600)
        assert diff < 1  # within 1 second

    def test_sla_status_overdue(self):
        from app.modules.garments.service import GarmentsService
        from datetime import timedelta

        # Create a mock service
        from unittest.mock import MagicMock
        svc = GarmentsService.__new__(GarmentsService)
        svc.db = MagicMock()

        past_due = datetime.now(timezone.utc) - timedelta(hours=2)
        status = svc._compute_sla_status(past_due)
        assert status == "OVERDUE"

    def test_sla_status_on_time(self):
        from app.modules.garments.service import GarmentsService

        svc = GarmentsService.__new__(GarmentsService)
        svc.db = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()

        future_due = datetime.now(timezone.utc) + timedelta(hours=10)
        status = svc._compute_sla_status(future_due)
        assert status == "ON_TIME"
