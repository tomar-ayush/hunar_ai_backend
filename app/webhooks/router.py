from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from typing import Optional, Dict, Any
from pydantic import BaseModel
import uuid

from app.database import get_session
from app.calls.model import CallSession
from app.worker.tasks import extract_transcript

router = APIRouter(prefix="/webhooks")

class VoiceCallPayload(BaseModel):
    external_call_id: str
    status: str
    transcript: Optional[Dict[str, Any]] = None
    recording_url: Optional[str] = None

@router.post("/voice-call")
def voice_call_webhook(payload: VoiceCallPayload, session: Session = Depends(get_session)):
    call_session = session.exec(
        select(CallSession).where(CallSession.external_call_id == payload.external_call_id)
    ).first()
    
    if not call_session:
        return {"status": "ignored", "detail": "session not found"}
        
    if call_session.status in ["completed", "failed"]:
        return {"status": "ignored", "detail": "already processed"}
        
    call_session.status = payload.status
    call_session.transcript = payload.transcript
    call_session.recording_url = payload.recording_url
    
    session.add(call_session)
    session.commit()
    
    if payload.status == "completed":
        extract_transcript.delay(str(call_session.id))
        
    return {"status": "success"}
