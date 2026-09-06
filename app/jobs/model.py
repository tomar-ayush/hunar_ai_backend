from sqlmodel import SQLModel, Field, JSON, Column
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

class Job(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    title: str
    jd_text: str
    agent_id: Optional[str] = Field(default=None, description="Hunar AI voice agent ID for this job")
    target_seniority_level: Optional[str] = None
    target_location: Optional[str] = None
    experience_required: Optional[str] = None
    required_skills: Optional[List[str]] = Field(default_factory=list, sa_column=Column(JSON))
    script: Optional[Dict[str, Any]] = Field(default_factory=dict, sa_column=Column(JSON))
    sourcing_mode: str = "auto"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
