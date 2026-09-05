from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Dict, Any, Optional

class CallSessionCreate(BaseModel):
    candidate_id: UUID
    status: str
    external_call_id: Optional[str] = None

class CallSessionRead(BaseModel):
    id: UUID
    candidate_id: UUID
    status: str
    transcript: Dict[str, Any]
    recording_url: Optional[str]
    duration: int
    external_call_id: Optional[str]
    created_at: datetime

class AnswerCreate(BaseModel):
    call_session_id: UUID
    question: str
    extracted_answer: str
    confidence: float

class AnswerRead(AnswerCreate):
    id: UUID

class ScoreCreate(BaseModel):
    call_session_id: UUID
    score: int
    reasoning: str

class ScoreRead(ScoreCreate):
    id: UUID
