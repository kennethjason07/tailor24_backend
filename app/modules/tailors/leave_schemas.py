"""Leave requests schemas."""
from __future__ import annotations
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field
from app.common.enums import LeaveStatus


class LeaveRequestCreate(BaseModel):
    fromDate: date
    toDate: date
    reason: str = Field(..., min_length=5)


class LeaveReviewRequest(BaseModel):
    status: LeaveStatus
    notes: Optional[str] = None
