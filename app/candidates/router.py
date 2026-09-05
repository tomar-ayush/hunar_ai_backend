from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
import uuid

from app.database import get_session
from app.auth.service import get_current_user
from app.auth.model import User
from app.candidates.model import Candidate
from app.jobs.model import Job
from app.worker.tasks import trigger_call


router = APIRouter(prefix="/candidates", tags=["Candidates"])


@router.post("/{id}/call", status_code=status.HTTP_202_ACCEPTED)
def call_candidate(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Enqueue an outbound AI voice call to a candidate.
    Returns 202 Accepted — the actual call happens asynchronously via Celery.
    """
    candidate = session.get(Candidate, id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Verify the candidate belongs to a job owned by this user's company
    job = session.get(Job, candidate.job_id)
    if not job or job.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Candidate not found")

    trigger_call.delay(str(candidate.id))
    return {"status": "accepted", "candidate_id": str(candidate.id)}
