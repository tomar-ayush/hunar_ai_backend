from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Dict, Any, Optional, List

class JobCreate(BaseModel):
    title: str
    jd_text: str
    agent_id: Optional[str] = None
    target_seniority_level: Optional[str] = None
    target_location: Optional[str] = None
    experience_required: Optional[str] = None
    required_skills: Optional[List[str]] = Field(default_factory=list)
    script: Optional[Dict[str, Any]] = Field(default_factory=dict)
    sourcing_mode: str = "auto"

class JobRead(JobCreate):
    id: UUID
    created_at: datetime

class JobUpdate(BaseModel):
    title: Optional[str] = None
    jd_text: Optional[str] = None
    agent_id: Optional[str] = None
    target_seniority_level: Optional[str] = None
    target_location: Optional[str] = None
    experience_required: Optional[str] = None
    required_skills: Optional[List[str]] = None
    script: Optional[Dict[str, Any]] = None
    sourcing_mode: Optional[str] = None
