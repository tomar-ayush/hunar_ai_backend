from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime


class ScrapedCandidateRead(BaseModel):
    id: Optional[UUID] = None
    job_id: Optional[UUID] = None
    name: str
    title: Optional[str] = ""
    company: Optional[str] = ""
    location: Optional[str] = ""
    skills: List[str] = Field(default_factory=list)
    email: Optional[str] = ""
    phone: Optional[str] = ""
    linkedin_url: Optional[str] = ""
    profile_url: Optional[str] = ""
    avatar_url: Optional[str] = ""
    source: str = "web_developer_directory"
    consent_status: str = "pending"
    created_at: Optional[datetime] = None


class ScrapeJobResponse(BaseModel):
    status: str = "success"
    job_id: UUID
    job_title: str
    filters_applied: Dict[str, Any] = Field(default_factory=dict)
    scraped_count: int
    saved_count: int
    candidates: List[ScrapedCandidateRead] = Field(default_factory=list)
