from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
import uuid

from app.database import get_session
from app.auth.service import get_current_user
from app.candidates.model import Candidate
from app.worker.tasks import trigger_call

router = APIRouter(prefix="/candidates", dependencies=[Depends(get_current_user)])

@router.post("/{id}/call", status_code=status.HTTP_202_ACCEPTED)
def call_candidate(id: uuid.UUID, session: Session = Depends(get_session)):
    candidate = session.get(Candidate, id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    trigger_call.delay(str(candidate.id))
    return {"status": "accepted"}
