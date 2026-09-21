"""Users module — admin user management."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.common.enums import UserRole


class UserCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., pattern=r"^\+?[0-9]{10,15}$")
    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=6)
    role: UserRole


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    isActive: Optional[bool] = None


class UserResponse(BaseModel):
    id: str
    name: str
    phone: str
    email: Optional[str]
    role: str
    isActive: bool
