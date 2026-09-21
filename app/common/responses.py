"""
TAILOR24 Backend — Standard API Response Wrappers
"""
from __future__ import annotations

from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard envelope for all successful API responses."""

    success: bool = True
    message: Optional[str] = None
    data: Optional[T] = None


class ErrorResponse(BaseModel):
    """Standard envelope for all error responses."""

    success: bool = False
    error_code: str
    message: str
    detail: Optional[Any] = None


def ok(data: Any = None, message: Optional[str] = None) -> dict:
    return {"success": True, "message": message, "data": data}


def error(error_code: str, message: str, detail: Any = None) -> dict:
    return {"success": False, "error_code": error_code, "message": message, "detail": detail}
