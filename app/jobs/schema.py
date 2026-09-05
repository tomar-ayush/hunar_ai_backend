from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Dict, Any

class JobCreate(BaseModel):
    company_id: UUID
    title: str
    jd_text: str
    script: Dict[str, Any]
    pass_criteria: str
    sourcing_mode: str

class JobRead(JobCreate):
    id: UUID
    created_at: datetime

class JobUpdate(BaseModel):
    title: str | None = None
    jd_text: str | None = None
    script: Dict[str, Any] | None = None
    pass_criteria: str | None = None
    sourcing_mode: str | None = None
