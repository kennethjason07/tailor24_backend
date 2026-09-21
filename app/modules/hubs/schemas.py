"""Hubs module schemas."""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


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
    managerUserId: Optional[str] = None
    isActive: Optional[bool] = None
    location: Optional[GeoPoint] = None
