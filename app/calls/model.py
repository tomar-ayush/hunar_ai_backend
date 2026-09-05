from sqlmodel import SQLModel, Field, JSON, Column
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class CallSession(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    candidate_id: UUID = Field(foreign_key="candidate.id")
    status: str
    transcript: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    recording_url: Optional[str] = None
    duration: int = 0
    external_call_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Answer(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    call_session_id: UUID = Field(foreign_key="callsession.id")
    question: str
    extracted_answer: str
    confidence: float

class Score(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    call_session_id: UUID = Field(foreign_key="callsession.id")
    score: int
    reasoning: str
