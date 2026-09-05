from sqlmodel import SQLModel, Field, JSON, Column
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class Job(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    company_id: Optional[UUID] = Field(default=None, index=True)
    title: str
    jd_text: str
    script: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    pass_criteria: str
    sourcing_mode: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
