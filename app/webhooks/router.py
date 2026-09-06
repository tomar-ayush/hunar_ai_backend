import json
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, Request, HTTPException
from sqlmodel import Session, select
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict

from app.database import get_session
from app.calls.model import CallSession
from app.worker.tasks import extract_transcript
from app.voice.service import VoiceAIClient
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class VoiceCallWebhookPayload(BaseModel):
    """
    Matches Hunar Voice Agents official webhook event payload.
    Supports events: call_summary, call_status_updated, call_recording_done, call_result_done.
    """
    event_type: Optional[str] = "call_summary"
    call_id: Optional[str] = None
    external_call_id: Optional[str] = None  # fallback for custom clients
    status: Optional[str] = None  # COMPLETED | NOT_CONNECTED | FAILED | CANCELLED
    duration_seconds: Optional[float] = None
    duration_minutes: Optional[float] = None
    recording_url: Optional[str] = None
    result: Optional[Dict[str, Any]] = None  # Hunar's AI extracted results
    transcript: Optional[Any] = None
    request_id: Optional[str] = None
    to_number: Optional[str] = None

    model_config = ConfigDict(extra="allow")


@router.post("/voice-call")
async def voice_call_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Official webhook receiver for Hunar.AI Voice Agents events.

    - Validates HMAC-SHA256 signature using HUNAR_API_KEY (from X-Hunar-Signature & X-Hunar-Timestamp)
    - Idempotent: checks external call ID before processing
    - Updates CallSession duration, recording_url, and structured result/transcript
    - Enqueues background Gemini LLM extraction if call is completed
    """
    body = await request.body()
    sig_header = request.headers.get("X-Hunar-Signature")
    timestamp_header = request.headers.get("X-Hunar-Timestamp")

    # 1. Validate signature using HUNAR_API_KEY if signature is present and key is configured
    if sig_header and settings.HUNAR_API_KEY:
        is_valid = VoiceAIClient.verify_webhook_signature(
            request_body=body,
            signature_header=sig_header,
            timestamp_header=timestamp_header,
            api_key=settings.HUNAR_API_KEY,
        )
        if not is_valid:
            logger.warning("Invalid Hunar webhook signature rejected")
            raise HTTPException(status_code=401, detail="Invalid signature")

    # 2. Parse payload
    try:
        raw_json = json.loads(body.decode("utf-8")) if body else {}
        payload = VoiceCallWebhookPayload(**raw_json)
    except Exception as e:
        logger.error(f"Failed to parse webhook JSON body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    effective_call_id = payload.call_id or payload.external_call_id
    if not effective_call_id:
        return {"status": "ignored", "detail": "missing call_id"}

    # 3. Locate CallSession by external_call_id or request_id
    call_session = session.exec(
        select(CallSession).where(
            CallSession.external_call_id == effective_call_id
        )
    ).first()

    # Fallback to match by request_id (candidate ID) if external_call_id was not yet stored
    if not call_session and payload.request_id:
        try:
            import uuid
            candidate_uuid = uuid.UUID(payload.request_id)
            call_session = session.exec(
                select(CallSession).where(CallSession.candidate_id == candidate_uuid)
            ).first()
            if call_session:
                call_session.external_call_id = effective_call_id
        except ValueError:
            pass

    if not call_session:
        logger.warning(f"Webhook received for unknown call: {effective_call_id}")
        return {"status": "ignored", "detail": "session not found"}

    # 4. Idempotency check: don't re-process if already in terminal state with extraction done
    norm_status = (payload.status or "completed").lower()
    if call_session.status in ["completed", "failed"] and norm_status in ["completed", "failed"]:
        logger.info(f"Idempotent skip: call {effective_call_id} already marked as {call_session.status}")
        return {"status": "ignored", "detail": "already processed"}

    # 5. Update call session fields
    call_session.status = norm_status
    if payload.recording_url:
        call_session.recording_url = payload.recording_url
    if payload.duration_seconds is not None:
        call_session.duration = int(payload.duration_seconds)
    elif payload.duration_minutes is not None:
        call_session.duration = int(payload.duration_minutes * 60)

    # Store transcript or structured result
    if payload.result:
        call_session.transcript = payload.result
    elif payload.transcript:
        call_session.transcript = payload.transcript

    session.add(call_session)
    session.commit()
    session.refresh(call_session)

    logger.info(f"Webhook updated call {effective_call_id}: status={call_session.status}")

    # 6. Trigger background extraction task for completed calls
    if norm_status == "completed":
        background_tasks.add_task(extract_transcript, str(call_session.id))
        logger.info(f"Enqueued background extraction task for call_session {call_session.id}")

    return {"status": "success", "call_id": effective_call_id}
