import asyncio
from typing import Optional
from sqlmodel import Session
from app.worker.celery_app import celery_app
from app.database import engine
from app.candidates.model import Candidate
from app.calls.model import CallSession, Answer, Score
from app.voice.service import VoiceAIClient
from app.llm.service import LLMClient

@celery_app.task(name="tasks.trigger_call")
def trigger_call(candidate_id: str) -> Optional[str]:
    with Session(engine) as session:
        candidate = session.get(Candidate, candidate_id)
        if not candidate:
            return None
            
        voice_client = VoiceAIClient()
        script = {"intro": f"Hello {getattr(candidate, 'name', 'Candidate')}, this is a mock interview."}
        
        phone = getattr(candidate, 'phone', '555-0000')
        external_call_id = asyncio.run(voice_client.trigger_outbound_call(phone, script))
        
        call_session = CallSession(
            candidate_id=candidate.id,
            external_call_id=external_call_id,
            status="in_progress"
        )
        session.add(call_session)
        session.commit()
        
        return external_call_id

@celery_app.task(name="tasks.extract_transcript")
def extract_transcript(call_session_id: str) -> bool:
    with Session(engine) as session:
        call_session = session.get(CallSession, call_session_id)
        if not call_session:
            return False
            
        llm_client = LLMClient()
        
        transcript = [{"speaker": "AI", "text": "Hello"}, {"speaker": "Candidate", "text": "Hi"}]
        questions = ["What is your experience with FastAPI?"]
        pass_criteria = "Must know FastAPI and SQLModel"
        
        answers = asyncio.run(llm_client.extract_answers_from_transcript(transcript, questions))
        score_data = asyncio.run(llm_client.score_transcript(transcript, pass_criteria))
        
        for ans in answers:
            answer_record = Answer(
                call_session_id=call_session.id,
                question=ans["question"],
                extracted_answer=ans["extracted_answer"],
                confidence=ans["confidence"]
            )
            session.add(answer_record)
            
        score_record = Score(
            call_session_id=call_session.id,
            score=score_data["score"],
            reasoning=score_data["reasoning"]
        )
        session.add(score_record)
        
        call_session.status = "completed"
        session.add(call_session)
        session.commit()
        
        return True
