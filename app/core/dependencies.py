"""
TAILOR24 Backend — FastAPI Dependencies
Role guards and current-user resolution.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.common.enums import UserRole
from app.common.exceptions import AuthenticationError, AuthorizationError
from app.core.database import get_db
from app.core.security import decode_token
from bson import ObjectId
from jose import JWTError

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


def _get_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "AUTHENTICATION_FAILED", "message": "Bearer token required"},
        )
    return credentials.credentials


def get_current_user(token: str = Depends(_get_token)) -> dict:
    """
    Decode the JWT and load the user document from MongoDB.
    Role is read from the database — never trusted from the token alone.
    """
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "AUTHENTICATION_FAILED", "message": "Invalid or expired token"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "AUTHENTICATION_FAILED", "message": "Token missing subject"},
        )

    db = get_db()
    user = db.users.find_one({"_id": ObjectId(user_id), "isActive": True})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "AUTHENTICATION_FAILED", "message": "User not found or inactive"},
        )
    return user


def _require_role(*roles: UserRole):
    """Factory that returns a dependency enforcing one of the given roles."""

    def dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in [r.value for r in roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": "FORBIDDEN",
                    "message": f"Role {current_user.get('role')!r} is not authorized for this action",
                },
            )
        return current_user

    return dependency


# Convenience role dependencies
require_customer = _require_role(UserRole.CUSTOMER)
require_tailor = _require_role(UserRole.TAILOR)
require_hub_staff = _require_role(UserRole.HUB_STAFF, UserRole.HUB_MANAGER)
require_hub_manager = _require_role(UserRole.HUB_MANAGER)
require_rider = _require_role(UserRole.RIDER)
require_admin_finance = _require_role(UserRole.ADMIN_FINANCE)

# Staff or manager
require_hub_ops = _require_role(UserRole.HUB_STAFF, UserRole.HUB_MANAGER)

# Any authenticated user
require_any = get_current_user
