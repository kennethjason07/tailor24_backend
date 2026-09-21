"""Addresses schemas."""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class GeoPoint(BaseModel):
    type: str = "Point"
    coordinates: List[float] = Field(..., min_length=2, max_length=2)


class AddressCreateRequest(BaseModel):
    label: str = Field(..., description="Home / Work / Other")
    recipientName: str
    phone: str
    addressLine1: str
    addressLine2: Optional[str] = None
    city: str
    state: str
    pincode: str = Field(..., pattern=r"^\d{6}$")
    location: Optional[GeoPoint] = None
    isDefault: bool = False


class AddressUpdateRequest(BaseModel):
    label: Optional[str] = None
    recipientName: Optional[str] = None
    phone: Optional[str] = None
    addressLine1: Optional[str] = None
    addressLine2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    location: Optional[GeoPoint] = None
    isDefault: Optional[bool] = None
