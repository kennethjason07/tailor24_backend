"""Tests: auth, user creation, authorization."""
from __future__ import annotations

import pytest
from tests.conftest import create_test_user, get_token, auth_headers


class TestAuth:
    def test_register_customer(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "name": "Test Customer",
            "phone": "+919900000001",
            "password": "Test@12345",
            "role": "CUSTOMER",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "CUSTOMER"

    def test_register_duplicate_phone(self, client):
        payload = {"name": "Dup", "phone": "+919900000001", "password": "Test@12345", "role": "CUSTOMER"}
        client.post("/api/v1/auth/register", json=payload)
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 409

    def test_register_admin_role_denied(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "name": "Fake Admin",
            "phone": "+919900000099",
            "password": "Test@12345",
            "role": "ADMIN_FINANCE",
        })
        assert resp.status_code == 400

    def test_login_success(self, client, db):
        create_test_user(db, "Login Test", "+919900000010", "CUSTOMER")
        token = get_token(client, "+919900000010")
        assert token and len(token) > 20

    def test_login_wrong_password(self, client, db):
        create_test_user(db, "WrongPass", "+919900000011", "CUSTOMER")
        resp = client.post("/api/v1/auth/login", json={"phone": "+919900000011", "password": "wrongpass"})
        assert resp.status_code == 401

    def test_login_unknown_phone(self, client):
        resp = client.post("/api/v1/auth/login", json={"phone": "+919999999999", "password": "anypass"})
        assert resp.status_code == 401

    def test_get_me(self, client, db):
        create_test_user(db, "Me Test", "+919900000012", "CUSTOMER")
        token = get_token(client, "+919900000012")
        resp = client.get("/api/v1/auth/me", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["data"]["phone"] == "+919900000012"
        assert "passwordHash" not in resp.json()["data"]

    def test_me_unauthenticated(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_token_refresh(self, client, db):
        create_test_user(db, "Refresh Test", "+919900000013", "CUSTOMER")
        resp = client.post("/api/v1/auth/login", json={"phone": "+919900000013", "password": "Test@12345"})
        refresh_token = resp.json()["data"]["refresh_token"]
        resp2 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp2.status_code == 200
        assert "access_token" in resp2.json()["data"]


class TestAuthorization:
    def test_customer_cannot_access_admin_endpoint(self, client, db):
        create_test_user(db, "Cust Auth", "+919900000020", "CUSTOMER")
        token = get_token(client, "+919900000020")
        resp = client.get("/api/v1/users", headers=auth_headers(token))
        assert resp.status_code == 403

    def test_hub_manager_role_required(self, client, db):
        create_test_user(db, "Staff No Mgr", "+919900000021", "HUB_STAFF")
        token = get_token(client, "+919900000021")
        resp = client.patch(
            "/api/v1/payouts/claims/000000000000000000000001/manager-review",
            headers=auth_headers(token),
            json={"approve": True},
        )
        assert resp.status_code == 403

    def test_role_read_from_db_not_token(self, client, db):
        """
        Verifies that authorization uses the role from MongoDB,
        not a value that could be forged in the token.
        """
        user = create_test_user(db, "Role Test", "+919900000022", "CUSTOMER")
        # Create a token claiming ADMIN_FINANCE role
        from app.core.security import create_access_token
        fake_token = create_access_token(
            subject=str(user["_id"]),
            role="ADMIN_FINANCE",  # claimed role
        )
        # But the DB has role=CUSTOMER — access should be denied
        resp = client.get("/api/v1/users", headers={"Authorization": f"Bearer {fake_token}"})
        assert resp.status_code == 403
