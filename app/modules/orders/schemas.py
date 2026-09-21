"""Orders and Garments Pydantic schemas."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.common.enums import GarmentType, GenderCategory, PaymentMethod


# ── Measurements ─────────────────────────────────────────────────────────────


class Measurements(BaseModel):
    """
    Flexible measurements schema supporting all garment types.
    standard: named standard sizes (S, M, L, XL …)
    custom: key-value pairs for any measurement dimension
    unit: cm | inch
    """

    unit: str = Field(default="cm", pattern=r"^(cm|inch)$")
    standard: Optional[str] = None  # S / M / L / 36 / 38 …
    custom: Optional[Dict[str, Any]] = None  # {"chest": 40, "waist": 34, …}


# ── Garment line item inside an order request ─────────────────────────────────


class GarmentItem(BaseModel):
    type: GarmentType
    gender: GenderCategory
    serviceCharge: Decimal = Field(..., gt=0, decimal_places=2)
    measurements: Measurements
    notes: Optional[str] = None


# ── Order creation ────────────────────────────────────────────────────────────


class PickupSlot(BaseModel):
    date: str  # ISO date string
    startTime: str  # "10:00"
    endTime: str  # "11:00"


class OrderCreateRequest(BaseModel):
    addressId: str
    hubId: str
    pickupSlot: PickupSlot
    paymentMethod: PaymentMethod
    garments: List[GarmentItem] = Field(..., min_length=1)


# ── Scan / workflow action ────────────────────────────────────────────────────


class GarmentScanRequest(BaseModel):
    action: str = Field(..., description="Target stage e.g. CUTTING_STARTED")
    hubId: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
