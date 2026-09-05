from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class CandidateCreate(BaseModel):
    job_id: UUID
    name: str
    phone: str
    email: str
    source: str
    consent_status: str

class CandidateRead(CandidateCreate):
    id: UUID
    created_at: datetime
