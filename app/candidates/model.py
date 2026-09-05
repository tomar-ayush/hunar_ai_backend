from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone

class Candidate(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    job_id: UUID = Field(foreign_key="job.id")
    name: str
    phone: str
    email: str
    source: str
    consent_status: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
