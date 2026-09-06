from sqlmodel import SQLModel, Field, Column, JSON
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional, List


class Candidate(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    job_id: UUID = Field(foreign_key="job.id")
    name: str
    phone: str = Field(default="")
    email: str = Field(default="")
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    profile_url: Optional[str] = None
    avatar_url: Optional[str] = None
    skills: Optional[List[str]] = Field(default_factory=list, sa_column=Column(JSON))
    source: str = Field(default="manual_upload")
    consent_status: str = Field(default="pending")
    call_id: Optional[str] = Field(default=None, description="Hunar AI external call ID mapping this candidate to their call")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
