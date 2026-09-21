from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field

class CustomerProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    profilePhotoUrl: Optional[str] = None
