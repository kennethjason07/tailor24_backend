"""Hubs module schemas."""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field


class GeoPoint(BaseModel):
    type: str = "Point"
    coordinates: List[float] = Field(..., min_length=2, max_length=2,
                                      description="[longitude, latitude]")


class HubCreateRequest(BaseModel):
    name: str = Field(..., min_length=2)
    code: str = Field(..., pattern=r"^[A-Z0-9_-]{2,20}$")
    addressLine1: str
    addressLine2: Optional[str] = None
    city: str
    state: str
    pincode: str
    location: Optional[GeoPoint] = None
    contactPhone: str
    managerUserId: Optional[str] = None


class HubUpdateRequest(BaseModel):
    name: Optional[str] = None
    contactPhone: Optional[str] = None
    addressLine1: Optional[str] = None
    addressLine2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    managerUserId: Optional[str] = None
    isActive: Optional[bool] = None
    location: Optional[GeoPoint] = None


class HubManagerCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., pattern=r"^\+?[0-9]{10,15}$")
    password: str = Field(..., min_length=6)
    email: Optional[EmailStr] = None
