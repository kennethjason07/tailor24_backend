"""Tailors module schemas."""
from __future__ import annotations
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field
from app.common.enums import GarmentType, GenderCategory, TailorAvailability


class GeoPoint(BaseModel):
    type: str = "Point"
    coordinates: List[float] = Field(..., min_length=2, max_length=2)


class PayoutInfo(BaseModel):
    bankName: Optional[str] = None
    accountNumber: Optional[str] = None
    ifscCode: Optional[str] = None
    upiId: Optional[str] = None


class TailorProfileCreateRequest(BaseModel):
    hubId: str
    genderSpecialization: List[GenderCategory]
    skills: List[GarmentType]
    dailyCapacity: int = Field(default=10, ge=1, le=200)
    payoutInfo: Optional[PayoutInfo] = None


class TailorProfileUpdateRequest(BaseModel):
    hubId: Optional[str] = None
    genderSpecialization: Optional[List[GenderCategory]] = None
    skills: Optional[List[GarmentType]] = None
    dailyCapacity: Optional[int] = Field(default=None, ge=1, le=200)
    availability: Optional[TailorAvailability] = None
    location: Optional[GeoPoint] = None
    payoutInfo: Optional[PayoutInfo] = None


class TailorAvailabilityUpdate(BaseModel):
    availability: TailorAvailability


class TailorLocationUpdate(BaseModel):
    location: GeoPoint
