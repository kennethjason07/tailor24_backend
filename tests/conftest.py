"""
TAILOR24 — pytest configuration and shared fixtures.
Uses mongomock or a real test MongoDB instance.
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from decimal import Decimal

from bson import ObjectId, Decimal128
from fastapi.testclient import TestClient

# Point to a test database
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGODB_DATABASE", "tailor24_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-not-production")
os.environ.setdefault("APP_ENV", "development")


@pytest.fixture(scope="session")
def mongo_db():
    """
    Provide a real MongoDB test database (or mongomock if available).
    Drops all test collections after the session.
    """
    try:
        import mongomock
        client = mongomock.MongoClient()
        db = client["tailor24_test"]
    except ImportError:
        from pymongo import MongoClient
        client = MongoClient(os.environ["MONGODB_URI"])
        db = client["tailor24_test"]

    yield db

    # Cleanup
    for coll in db.list_collection_names():
        db.drop_collection(coll)
    client.close()


@pytest.fixture(scope="session")
def app(mongo_db):
    """Create a FastAPI test app wired to the test DB."""
    import app.core.database as db_module
    db_module._db = mongo_db
    db_module._client = mongo_db.client

    # Initialize collections and indexes
    from app.scripts.init_db import init_collections, init_indexes
    init_collections(mongo_db)
    try:
        init_indexes(mongo_db)
    except Exception:
        pass  # mongomock may not support all index types

    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)


@pytest.fixture
def db(mongo_db):
    return mongo_db


# ── Auth helpers ──────────────────────────────────────────────────────────────

def create_test_user(db, name: str, phone: str, role: str, password: str = "Test@12345") -> dict:
    from app.core.security import hash_password
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    doc = {
        "name": name,
        "phone": phone,
        "email": None,
        "role": role,
        "passwordHash": hash_password(password),
        "isActive": True,
        "createdAt": now,
        "updatedAt": now,
    }
    existing = db.users.find_one({"phone": phone})
    if existing:
        return existing
    result = db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def get_token(client, phone: str, password: str = "Test@12345") -> str:
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
