from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import Optional
import uuid

from app.database import get_session
from app.candidates.model import Candidate
from app.candidates.schema import TriggerCallRequest
from app.jobs.model import Job
from app.calls.model import CallSession
from app.voice.service import VoiceAIClient
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


@router.get("/{id}/call-details")
async def get_candidate_call_details(
    id: uuid.UUID,
    session: Session = Depends(get_session),
):
    """
    Get the call details of a candidate from Hunar Voice API via candidate_id.
    Calls Hunar API: GET /external/v1/calls/{call_id}/
    Returns all call attributes including callee_name, mobile_number, agent_id,
    duration, recording_url, and the evaluation result (summary, answers, suitability_score).
    """
    candidate = session.get(Candidate, id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not candidate.call_id:
        raise HTTPException(
            status_code=400,
            detail="No call has been triggered for this candidate yet (candidate.call_id is empty).",
        )

    client = VoiceAIClient()
    try:
        call_details = await client.get_call_details(candidate.call_id)
        if isinstance(call_details, dict) and call_details:
            call_details.setdefault("call_id", candidate.call_id)
            call_details.setdefault("candidate_id", str(candidate.id))
            return call_details
    except Exception as e:
        # Fall back to local DB if Hunar API is temporarily unreachable
        call_session = session.exec(
            select(CallSession).where(CallSession.external_call_id == candidate.call_id)
        ).first()
        if call_session:
            return {
                "id": candidate.call_id,
                "call_id": candidate.call_id,
                "candidate_id": str(candidate.id),
                "callee_name": candidate.name,
                "mobile_number": candidate.phone,
                "status": (call_session.status or "COMPLETED").upper(),
                "duration_seconds": call_session.duration,
                "recording_url": call_session.recording_url,
                "result": call_session.transcript or {},
            }
        raise HTTPException(status_code=500, detail=f"Failed to fetch call details from Hunar: {e}")

    # If call_details came back empty
    call_session = session.exec(
        select(CallSession).where(CallSession.external_call_id == candidate.call_id)
    ).first()
    if call_session:
        return {
            "id": candidate.call_id,
            "call_id": candidate.call_id,
            "candidate_id": str(candidate.id),
            "callee_name": candidate.name,
            "mobile_number": candidate.phone,
            "status": (call_session.status or "COMPLETED").upper(),
            "duration_seconds": call_session.duration,
            "recording_url": call_session.recording_url,
            "result": call_session.transcript or {},
        }

    return {"call_id": candidate.call_id, "candidate_id": str(candidate.id), "status": "UNKNOWN"}
