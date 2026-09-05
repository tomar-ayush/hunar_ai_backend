from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone

class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    company_id: UUID = Field(default_factory=uuid4)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
