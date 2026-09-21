"""Tests: health endpoint, MongoDB connection, dashboard aggregation."""
from __future__ import annotations

import pytest


class TestHealth:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "database" in data

    def test_docs_available(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_openapi_json(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        openapi = resp.json()
        assert openapi["info"]["title"] == "TAILOR24 Backend API"
        assert "/api/v1/garments/{garment_id}/scan" in str(openapi["paths"])


class TestDatabaseConnection:
    def test_mongo_connection(self, db):
        """Verify the test MongoDB is reachable."""
        assert db is not None
        # Insert and retrieve a test document
        result = db.get_collection("_test_conn").insert_one({"ping": True})
        doc = db.get_collection("_test_conn").find_one({"_id": result.inserted_id})
        assert doc["ping"] is True
        db.get_collection("_test_conn").delete_many({})


class TestTransitionEngine:
    def test_all_valid_transitions_from_table(self):
        from app.common.enums import GarmentStage, UserRole, VALID_TRANSITIONS
        from app.modules.garments.transition_engine import validate_transition

        # Every edge in VALID_TRANSITIONS must validate cleanly
        # We use a permissive role (HUB_MANAGER) to check structural validity
        for current, nexts in VALID_TRANSITIONS.items():
            for nxt in nexts:
                try:
                    # RIDER is required for OUT_FOR_DELIVERY and DELIVERED/DELIVERY_FAILED
                    role = UserRole.RIDER if nxt in (GarmentStage.DELIVERED, GarmentStage.DELIVERY_FAILED, GarmentStage.OUT_FOR_DELIVERY) else UserRole.HUB_MANAGER
                    validate_transition(current, nxt, role)
                except Exception as e:
                    pytest.fail(f"Valid transition {current}→{nxt} raised: {e}")

    def test_terminal_states_have_no_outgoing_transitions(self):
        from app.common.enums import GarmentStage, VALID_TRANSITIONS
        terminals = {GarmentStage.DELIVERED}
        for t in terminals:
            assert VALID_TRANSITIONS[t] == set(), f"{t} should be terminal"

    def test_qr_format_validation(self):
        from app.modules.garments.qr_service import is_valid_qr_value, generate_qr_value
        assert is_valid_qr_value("GRT-T24-000000001")
        assert is_valid_qr_value(generate_qr_value(999999999))
        assert not is_valid_qr_value("GRT-T24-1")  # too short
        assert not is_valid_qr_value("INVALID-QR")
        assert not is_valid_qr_value("")
