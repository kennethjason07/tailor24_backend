"""Schemas for Hub Manager Credential Management."""
from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field


class CreateRiderRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., pattern=r"^\+?[0-9]{10,15}$")
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)
    emergencyContact: Optional[str] = None
    address: Optional[str] = None


class CreateWorkerRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., pattern=r"^\+?[0-9]{10,15}$")
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)
    role: str = Field(default="HUB_STAFF")



class CreateTailorAccountRequest(BaseModel):
    applicationId: Optional[str] = None
    password: Optional[str] = Field(None, min_length=6)


class CreateTailorDirectRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., pattern=r"^\+?[0-9]{10,15}$")
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)
    skills: Optional[List[str]] = None
    genderSpecialization: Optional[List[str]] = None




class ActivateAccountRequest(BaseModel):
    activationToken: str = Field(..., min_length=10)
    password: str = Field(..., min_length=6)


class UserCredentialResponse(BaseModel):
    userId: str
    name: str
    phone: str
    email: Optional[str] = None
    role: str
    hubId: Optional[str] = None
    isActive: bool = True
    accountStatus: str = "PENDING_ACTIVATION"
    activationToken: Optional[str] = None
    activationExpiresAt: Optional[str] = None
    activationLink: Optional[str] = None
    lastLoginAt: Optional[str] = None
    createdAt: Optional[str] = None
    emergencyContact: Optional[str] = None
    address: Optional[str] = None
    skills: Optional[List[str]] = None
    genderSpecialization: Optional[List[str]] = None
    dailyCapacity: Optional[int] = None
    availabilityStatus: Optional[str] = None


class ResetAccessResponse(BaseModel):
    userId: str
    name: str
    phone: str
    role: str
    accountStatus: str
    activationToken: str
    activationExpiresAt: str
    activationLink: str


class AuditLogResponse(BaseModel):
    id: str
    actorUserId: str
    actorRole: str
    targetUserId: str
    targetRole: str
    hubId: str
    action: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None
