"""
TAILOR24 Backend — PyMongo / Pydantic Helpers
Utilities for serializing MongoDB documents to Pydantic-compatible dicts.
"""
from __future__ import annotations

import re
from bson import ObjectId, Decimal128
from decimal import Decimal
from typing import Any, Dict


def object_id_str(value: Any) -> str:
    """Convert ObjectId to string."""
    return str(value)


def is_valid_object_id(value: str) -> bool:
    """Return True if value is a valid 24-hex-char ObjectId string."""
    return bool(re.fullmatch(r"[a-fA-F0-9]{24}", value))


def to_object_id(value: str) -> ObjectId:
    """Convert string to ObjectId, raising ValueError if invalid."""
    if not is_valid_object_id(value):
        raise ValueError(f"Invalid ObjectId: {value!r}")
    return ObjectId(value)


def decimal_to_str(value: Decimal128) -> str:
    return str(value)


def doc_to_dict(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively convert a MongoDB document to a JSON-serializable dict.
    - ObjectId → str
    - Decimal128 → str (monetary values — preserves precision)
    """
    result = {}
    for k, v in doc.items():
        key = "id" if k == "_id" else k
        result[key] = _convert(v)
    return result


def _convert(v: Any) -> Any:
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, Decimal128):
        return str(v)
    if isinstance(v, dict):
        return {("id" if k == "_id" else k): _convert(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_convert(item) for item in v]
    return v


def money_to_decimal128(value: Any) -> Decimal128:
    """Convert Decimal, float, int, or string to Decimal128 for MongoDB storage."""
    return Decimal128(str(Decimal(str(value)).quantize(Decimal("0.01"))))
