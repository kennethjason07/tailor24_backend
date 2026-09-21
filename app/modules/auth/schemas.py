"""Auth module schemas."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    phone: str = Field(..., description="User phone number (used as username)")
    password: str = Field(..., min_length=6)


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., pattern=r"^\+?[0-9]{10,15}$")
    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=6)
    role: str = Field(default="CUSTOMER")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str

class SendOtpRequest(BaseModel):
    email: EmailStr

class VerifyOtpLoginRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)

class VerifyOtpRegisterRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., pattern=r"^\+?[0-9]{10,15}$")
    role: str = Field(default="CUSTOMER")
