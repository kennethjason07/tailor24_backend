"""
TAILOR24 Backend — Custom Exception Hierarchy
"""
from __future__ import annotations

from typing import Any, Optional


class AppError(Exception):
    """Base application error."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, detail: Optional[Any] = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    error_code = "CONFLICT"


class ValidationError(AppError):
    status_code = 400
    error_code = "VALIDATION_ERROR"


class BusinessRuleError(AppError):
    status_code = 400
    error_code = "BUSINESS_RULE_VIOLATION"


class AuthenticationError(AppError):
    status_code = 401
    error_code = "AUTHENTICATION_FAILED"


class AuthorizationError(AppError):
    status_code = 403
    error_code = "FORBIDDEN"


class InvalidTransitionError(BusinessRuleError):
    error_code = "INVALID_GARMENT_TRANSITION"


class DuplicatePayoutError(ConflictError):
    error_code = "DUPLICATE_PAYOUT"


class TailorUnavailableError(BusinessRuleError):
    error_code = "TAILOR_UNAVAILABLE"


class CapacityExceededError(BusinessRuleError):
    error_code = "CAPACITY_EXCEEDED"


class SLAError(AppError):
    status_code = 400
    error_code = "SLA_ERROR"
