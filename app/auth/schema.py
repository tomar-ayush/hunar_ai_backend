from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime

class UserCreate(BaseModel):
    company_id: UUID
    email: EmailStr
    password: str

class UserRead(BaseModel):
    id: UUID
    company_id: UUID
    email: EmailStr
    created_at: datetime
