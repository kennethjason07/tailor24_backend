"""Auth service — registration, login, token refresh."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from pymongo.database import Database

from app.common.enums import UserRole
from app.common.exceptions import AuthenticationError, ConflictError, ValidationError
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    generate_otp,
    hash_otp,
    verify_otp,
)
from app.core.mail import send_otp_email
from jose import JWTError

logger = logging.getLogger(__name__)

# Roles that can self-register via the public endpoint
SELF_REGISTER_ROLES = {UserRole.CUSTOMER.value, UserRole.TAILOR.value}


class AuthService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.users = db.users
        self.auth_otps = db.auth_otps

    def register(
        self,
        name: str,
        phone: str,
        password: str,
        role: str = UserRole.CUSTOMER.value,
        email: Optional[str] = None,
    ) -> dict:
        if role not in SELF_REGISTER_ROLES:
            raise ValidationError(
                f"Self-registration is not allowed for role {role!r}. "
                "Contact an administrator."
            )

        if self.users.find_one({"phone": phone}):
            raise ConflictError(f"Phone number {phone!r} is already registered.")

        if email and self.users.find_one({"email": email}):
            raise ConflictError(f"Email {email!r} is already registered.")

        now = datetime.now(timezone.utc)
        doc = {
            "name": name,
            "phone": phone,
            "email": email,
            "role": role,
            "passwordHash": hash_password(password),
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
        }
        result = self.users.insert_one(doc)
        doc["_id"] = result.inserted_id
        logger.info("Registered user phone=%s role=%s", phone, role)
        return doc

    def login(self, phone: str, password: str) -> dict:
        user = self.users.find_one({"phone": phone})
        if not user or not verify_password(password, user.get("passwordHash", "")):
            raise AuthenticationError("Invalid phone number or password.")
        if not user.get("isActive", False):
            raise AuthenticationError("Account is deactivated. Contact support.")

        user_id = str(user["_id"])
        role = user["role"]
        access_token = create_access_token(subject=user_id, role=role)
        refresh_token = create_refresh_token(subject=user_id, role=role)
        logger.info("Login success user_id=%s role=%s", user_id, role)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    def refresh(self, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token)
        except JWTError:
            raise AuthenticationError("Invalid or expired refresh token.")

        if payload.get("type") != "refresh":
            raise AuthenticationError("Token is not a refresh token.")

        user_id = payload.get("sub")
        user = self.users.find_one({"_id": ObjectId(user_id), "isActive": True})
        if not user:
            raise AuthenticationError("User not found or inactive.")

        return self._generate_tokens(user)

    def _generate_tokens(self, user: dict) -> dict:
        user_id = str(user["_id"])
        role = user["role"]
        access_token = create_access_token(subject=user_id, role=role)
        new_refresh = create_refresh_token(subject=user_id, role=role)
        return {
            "access_token": access_token,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    async def send_otp(self, email: str) -> None:
        otp = generate_otp(6)
        otp_hash = hash_otp(otp)
        
        now = datetime.now(timezone.utc)
        self.auth_otps.update_one(
            {"email": email},
            {"$set": {"hash": otp_hash, "createdAt": now}},
            upsert=True
        )
        
        await send_otp_email(email, otp)

    def verify_otp_login(self, email: str, otp: str) -> dict:
        otp_doc = self.auth_otps.find_one({"email": email})
        if not otp_doc or not verify_otp(otp, otp_doc["hash"]):
            raise AuthenticationError("Invalid or expired OTP")
            
        user = self.users.find_one({"email": email})
        if not user or not user.get("isActive"):
            raise AuthenticationError("User not found or inactive")
            
        self.auth_otps.delete_one({"_id": otp_doc["_id"]})
        return self._generate_tokens(user)

    def verify_otp_register(
        self, email: str, otp: str, name: str, phone: str, role: str
    ) -> dict:
        otp_doc = self.auth_otps.find_one({"email": email})
        if not otp_doc or not verify_otp(otp, otp_doc["hash"]):
            raise AuthenticationError("Invalid or expired OTP")

        if role not in SELF_REGISTER_ROLES:
            raise ValidationError(f"Role {role!r} is not allowed to self-register.")

        if self.users.find_one({"phone": phone}):
            raise ConflictError(f"Phone number {phone!r} is already registered.")

        if self.users.find_one({"email": email}):
            raise ConflictError(f"Email {email!r} is already registered.")

        now = datetime.now(timezone.utc)
        doc = {
            "name": name,
            "phone": phone,
            "email": email,
            "role": role,
            "passwordHash": hash_password(generate_otp(12)),
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
        }
        result = self.users.insert_one(doc)
        doc["_id"] = result.inserted_id
        
        self.auth_otps.delete_one({"_id": otp_doc["_id"]})
        logger.info("OTP Registration successful user_id=%s role=%s", doc["_id"], role)
        return self._generate_tokens(doc)
