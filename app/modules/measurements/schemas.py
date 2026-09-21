from __future__ import annotations
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from app.common.enums import GenderCategory

class MeasurementValues(BaseModel):
    unit: str = Field(default="cm", pattern=r"^(cm|inch)$")
    values: Dict[str, float] = Field(default_factory=dict)
    custom: Dict[str, float] = Field(default_factory=dict)

class MeasurementProfileCreateRequest(BaseModel):
    profileName: str
    gender: GenderCategory
    measurements: MeasurementValues
    isDefault: bool = False

class MeasurementProfileUpdateRequest(BaseModel):
    profileName: Optional[str] = None
    gender: Optional[GenderCategory] = None
    measurements: Optional[MeasurementValues] = None
    isDefault: Optional[bool] = None

class GarmentMeasurementUpdateRequest(BaseModel):
    unit: str = Field(default="cm", pattern=r"^(cm|inch)$")
    values: Dict[str, float] = Field(default_factory=dict)
    custom: Dict[str, float] = Field(default_factory=dict)

class ClarificationRequest(BaseModel):
    note: str
