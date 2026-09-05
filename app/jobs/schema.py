from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Dict, Any, Optional

class JobCreate(BaseModel):
    title: str
    jd_text: str
    script: Dict[str, Any] = {}
    pass_criteria: str = ""
    sourcing_mode: str = "auto"
    company_id: Optional[UUID] = None

class JobRead(JobCreate):
    id: UUID
    created_at: datetime

class JobUpdate(BaseModel):
    title: Optional[str] = None
    jd_text: Optional[str] = None
    script: Optional[Dict[str, Any]] = None
    pass_criteria: Optional[str] = None
    sourcing_mode: Optional[str] = None
    company_id: Optional[UUID] = None
