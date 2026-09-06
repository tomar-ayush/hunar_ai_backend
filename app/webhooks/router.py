import json
import logging
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, Request, HTTPException
from sqlmodel import Session, select
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict

from app.database import get_session
from app.candidates.model import Candidate
from app.calls.model import CallSession
from app.worker.tasks import extract_transcript
from app.voice.service import VoiceAIClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class VoiceCallWebhookPayload(BaseModel):
    event_type: Optional[str] = "call_summary"
    call_id: Optional[str] = None
    external_call_id: Optional[str] = None
    status: Optional[str] = None
    duration_seconds: Optional[float] = None
    duration_minutes: Optional[float] = None
    recording_url: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    transcript: Optional[Any] = None
    request_id: Optional[str] = None
    to_number: Optional[str] = None

    model_config = ConfigDict(extra="allow")


@router.post("/hunar-call")
@router.post("/voice-call")
async def voice_call_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Webhook for Hunar AI calls.
    Sources call details from Hunar Voice API /external/v1/calls/{call_id}/
    and updates CallSession and Candidate call_id.
    """
    body = await request.body()
    try:
        raw_json = json.loads(body.decode("utf-8")) if body else {}
        payload = VoiceCallWebhookPayload(**raw_json)
    except Exception as e:
        logger.error(f"Failed to parse webhook JSON body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    effective_call_id = payload.call_id or payload.external_call_id or raw_json.get("id")
    if not effective_call_id:
        return {"status": "ignored", "detail": "missing call_id"}

    # Source call details directly from Hunar API
    voice_client = VoiceAIClient()
    try:
        hunar_data = await voice_client.get_call_details(effective_call_id)
    except Exception as e:
        logger.warning(f"Could not fetch from Hunar API, using payload: {e}")
        hunar_data = raw_json

    norm_status = (hunar_data.get("status") or payload.status or "completed").lower()
    recording_url = hunar_data.get("recording_url") or payload.recording_url
    result_data = hunar_data.get("result") or payload.result or {}
    duration_sec = hunar_data.get("duration_seconds") or payload.duration_seconds
    if duration_sec is None and hunar_data.get("duration_minutes") is not None:
        duration_sec = float(hunar_data["duration_minutes"]) * 60

    # Locate CallSession by external_call_id or candidate request_id
    call_session = session.exec(
        select(CallSession).where(CallSession.external_call_id == effective_call_id)
    ).first()

    req_id = hunar_data.get("request_id") or payload.request_id
    candidate = None
    if req_id:
        try:
            candidate = session.get(Candidate, uuid.UUID(req_id))
        except (ValueError, TypeError):
            pass

    if not candidate and call_session:
        candidate = session.get(Candidate, call_session.candidate_id)

    # As soon as we have call_id, update candidate table with call_id
    if candidate:
        candidate.call_id = effective_call_id
        session.add(candidate)

    if not call_session and candidate:
        call_session = CallSession(
            candidate_id=candidate.id,
            external_call_id=effective_call_id,
            status=norm_status,
        )
        session.add(call_session)

    if not call_session:
        logger.warning(f"Webhook received for unknown call: {effective_call_id}")
        return {"status": "ignored", "detail": "session not found"}

    # Update call session fields
    call_session.status = norm_status
    if recording_url:
        call_session.recording_url = recording_url
    if duration_sec is not None:
        call_session.duration = int(duration_sec)
    if result_data:
        call_session.transcript = result_data

    session.add(call_session)
    session.commit()
    session.refresh(call_session)

    # Trigger background extraction task for completed calls
    if norm_status == "completed":
        background_tasks.add_task(extract_transcript, str(call_session.id))

    return {
        "status": "success",
        "call_id": effective_call_id,
        "candidate_id": str(candidate.id) if candidate else None,
        "call_details": hunar_data,
    }
