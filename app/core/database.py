"""
TAILOR24 Backend — MongoDB Database Connection
Uses PyMongo synchronous client (motor available for async if needed).
"""
from __future__ import annotations

import logging
from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Optional[MongoClient] = None
_db: Optional[Database] = None


def connect_to_mongo() -> None:
    """Open the MongoDB connection. Called at application startup."""
    global _client, _db
    logger.info("Connecting to MongoDB Atlas …")
    _client = MongoClient(
        settings.MONGODB_URI,
        serverSelectionTimeoutMS=10_000,
        connectTimeoutMS=10_000,
        socketTimeoutMS=30_000,
    )
    _db = _client[settings.MONGODB_DATABASE]
    # Verify connectivity
    _client.admin.command("ping")
    logger.info("MongoDB connection established — db=%s", settings.MONGODB_DATABASE)


def close_mongo_connection() -> None:
    """Close the MongoDB connection. Called at application shutdown."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed.")


def get_db() -> Database:
    """Return the active database instance."""
    if _db is None:
        raise RuntimeError("Database not connected. Call connect_to_mongo() first.")
    return _db


def get_client() -> MongoClient:
    """Return the active MongoClient (for transactions)."""
    if _client is None:
        raise RuntimeError("Database not connected. Call connect_to_mongo() first.")
    return _client


def ping_db() -> bool:
    """Return True if the database is reachable."""
    try:
        if _client is None:
            return False
        _client.admin.command("ping")
        return True
    except Exception:
        return False
