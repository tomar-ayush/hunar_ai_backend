from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import Session
from typing import Optional
import uuid

from app.database import get_session
from app.candidates.model import Candidate
from app.candidates.schema import TriggerCallRequest
from app.jobs.model import Job
from app.worker.tasks import trigger_call


router = APIRouter(prefix="/candidates", tags=["Candidates"])


@router.post("/{id}/call", status_code=status.HTTP_202_ACCEPTED)
async def call_candidate(
    id: uuid.UUID,
    background_tasks: BackgroundTasks,
    payload: Optional[TriggerCallRequest] = None,
    session: Session = Depends(get_session),
):
    """
    Trigger an outbound AI voice call to a candidate.
    Allows frontend to pass custom `agent_id` and `phone_number` in the request body.
    Returns 202 Accepted — the call is triggered asynchronously in the background.
    """
    candidate = session.get(Candidate, id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    job = session.get(Job, candidate.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    agent_id = payload.agent_id if payload else None
    phone_number = payload.get_phone() if payload else None

    # Update candidate's phone if a new phone number was provided from the frontend
    if phone_number and phone_number.strip():
        candidate.phone = phone_number.strip()
        session.add(candidate)
        session.commit()
        session.refresh(candidate)

    effective_phone = (candidate.phone or "").strip()
    if not effective_phone:
        raise HTTPException(
            status_code=400,
            detail="Candidate phone number is missing. Please provide phone_number in the request body.",
        )

    background_tasks.add_task(
        trigger_call,
        candidate_id=str(candidate.id),
        agent_id=agent_id,
        phone_number=effective_phone,
    )

    return {
        "status": "accepted",
        "candidate_id": str(candidate.id),
        "agent_id": agent_id,
        "phone_number": effective_phone,
    }
