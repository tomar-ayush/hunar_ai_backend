from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, List


class CandidateCreate(BaseModel):
    job_id: UUID
    name: str
    phone: Optional[str] = ""
    email: Optional[str] = ""
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    profile_url: Optional[str] = None
    avatar_url: Optional[str] = None
    skills: Optional[List[str]] = Field(default_factory=list)
    source: str = "manual_upload"
    consent_status: str = "pending"


class CandidateRead(CandidateCreate):
    id: UUID
    created_at: datetime


class CandidateUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    profile_url: Optional[str] = None
    avatar_url: Optional[str] = None
    skills: Optional[List[str]] = None
    source: Optional[str] = None
    consent_status: Optional[str] = None


class TriggerCallRequest(BaseModel):
    agent_id: Optional[str] = Field(None, description="Hunar AI Voice Agent ID to use for the call")
    phone_number: Optional[str] = Field(None, description="Target phone number (overrides candidate phone if provided)")
    phone: Optional[str] = Field(None, description="Alternative alias for phone_number")

    def get_phone(self) -> Optional[str]:
        target = self.phone_number or self.phone
        return target.strip() if target else None
