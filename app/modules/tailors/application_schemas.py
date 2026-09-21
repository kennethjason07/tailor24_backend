"""Tailor applications schemas."""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field
from app.common.enums import ApplicationStatus, GarmentType, GenderCategory


class DocumentRef(BaseModel):
    name: str
    storageKey: str  # object storage key — no binary in MongoDB


class TailorApplicationRequest(BaseModel):
    hubId: str
    genderSpecialization: List[GenderCategory]
    skills: List[GarmentType]
    dailyCapacity: int = Field(default=10, ge=1)
    address: str
    aadharNumber: Optional[str] = None
    documents: List[DocumentRef] = []
    notes: Optional[str] = None


class ApplicationReviewRequest(BaseModel):
    status: ApplicationStatus
    notes: Optional[str] = None
