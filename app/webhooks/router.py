import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlmodel import Session, select
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

from app.database import get_session
from app.calls.model import CallSession
from app.worker.tasks import extract_transcript
from app.voice.service import VoiceAIClient
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class VoiceCallPayload(BaseModel):
    """Payload from Hunar.AI webhook callback."""
    external_call_id: str
    status: str  # "completed" | "failed" | "no_answer"
    transcript: Optional[List[Dict[str, Any]]] = None
    recording_url: Optional[str] = None
    duration: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


@router.post("/voice-call")
async def voice_call_webhook(
    request: Request,
    payload: VoiceCallPayload,
    session: Session = Depends(get_session),
):
    """
    Webhook endpoint for Hunar.AI voice call results.

    - Verifies the webhook signature (if configured)
    - Idempotent by external_call_id — ignores duplicate or already-processed calls
    - Stores transcript + recording
    - Enqueues LLM extraction task if call completed
    """
    # 1. Verify webhook signature
    signature = request.headers.get("x-hunar-signature", "")
    if settings.HUNAR_WEBHOOK_SECRET:
        body = await request.body()
        if not VoiceAIClient.verify_webhook_signature(
            body, signature, settings.HUNAR_WEBHOOK_SECRET
        ):
            logger.warning(f"Invalid webhook signature for call {payload.external_call_id}")
            raise HTTPException(status_code=401, detail="Invalid signature")

    # 2. Find the CallSession by external_call_id
    call_session = session.exec(
        select(CallSession).where(
            CallSession.external_call_id == payload.external_call_id
        )
    ).first()

    if not call_session:
        logger.warning(f"Webhook received for unknown call: {payload.external_call_id}")
        return {"status": "ignored", "detail": "session not found"}

    # 3. Idempotency check — don't reprocess completed/failed calls
    if call_session.status in ["completed", "failed"]:
        logger.info(f"Duplicate webhook for call {payload.external_call_id} — already {call_session.status}")
        return {"status": "ignored", "detail": "already processed"}

    # 4. Update the call session
    call_session.status = payload.status
    if payload.transcript:
        call_session.transcript = payload.transcript
    if payload.recording_url:
        call_session.recording_url = payload.recording_url
    if payload.duration:
        call_session.duration = payload.duration

    session.add(call_session)
    session.commit()

    logger.info(
        f"Webhook processed: call={payload.external_call_id}, status={payload.status}"
    )

    # 5. If completed, enqueue the LLM extraction task
    if payload.status == "completed" and payload.transcript:
        extract_transcript.delay(str(call_session.id))
        logger.info(f"Enqueued extraction for session {call_session.id}")

    return {"status": "success"}
