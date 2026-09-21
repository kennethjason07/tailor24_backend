"""
TAILOR24 Backend — Security Utilities
JWT token creation/validation, password hashing, OTP hashing.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt as _bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# ── Password ──────────────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """Hash a password with bcrypt. Input is truncated to 72 bytes (bcrypt limit)."""
    # bcrypt 5.x requires bytes; truncate to avoid ValueError
    return _bcrypt.hashpw(plain.encode("utf-8")[:72], _bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        return False


# ── OTP ───────────────────────────────────────────────────────────────────────


def generate_otp(length: int = 6) -> str:
    """Generate a cryptographically secure numeric OTP."""
    return "".join([str(secrets.randbelow(10)) for _ in range(length)])


def hash_otp(otp: str) -> str:
    """One-way hash of an OTP (SHA-256 with a secret pepper)."""
    pepper = settings.JWT_SECRET[:16]
    return hashlib.sha256(f"{pepper}:{otp}".encode()).hexdigest()


def verify_otp(plain_otp: str, stored_hash: str) -> bool:
    return hash_otp(plain_otp) == stored_hash


# ── JWT ───────────────────────────────────────────────────────────────────────


def create_access_token(
    subject: str,
    role: str,
    extra: Optional[Dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str, role: str) -> str:
    """Create a longer-lived refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT token. Raises JWTError on failure."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def is_token_expired(payload: Dict[str, Any]) -> bool:
    exp = payload.get("exp")
    if not exp:
        return True
    return datetime.now(timezone.utc) > datetime.fromtimestamp(exp, tz=timezone.utc)
