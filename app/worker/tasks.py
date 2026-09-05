import asyncio
import logging
from typing import Optional
from sqlmodel import Session, select

from app.worker.celery_app import celery_app
from app.database import engine
from app.candidates.model import Candidate
from app.jobs.model import Job
from app.calls.model import CallSession, Answer, Score
from app.voice.service import VoiceAIClient
from app.llm.service import LLMClient

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.trigger_call", bind=True, max_retries=3)
def trigger_call(self, candidate_id: str) -> Optional[str]:
    """
    Celery task: Trigger an outbound voice call via Hunar.AI.

    Flow:
    1. Load candidate + job from DB
    2. Build custom_data & resolve agent
    3. Call Hunar.AI Voice API (POST /external/v1/calls/)
    4. Store the external_call_id, set status=in_progress
    """
    with Session(engine) as session:
        candidate = session.get(Candidate, candidate_id)
        if not candidate:
            logger.error(f"Candidate {candidate_id} not found")
            return None

        # Load the job to get context & custom data
        job = session.get(Job, candidate.job_id)
        if not job:
            logger.error(f"Job {candidate.job_id} not found for candidate {candidate_id}")
            return None

        script_data = job.script or {}
        custom_data = {
            "job_role": job.title,
            "company": "Recruiter Portal",
            "candidate_name": candidate.name,
        }
        if isinstance(script_data.get("custom_data"), dict):
            custom_data.update(script_data["custom_data"])

        voice_client = VoiceAIClient()

        try:
            external_call_id = asyncio.run(
                voice_client.trigger_outbound_call(
                    candidate_phone=candidate.phone,
                    candidate_name=candidate.name,
                    custom_data=custom_data,
                    request_id=str(candidate.id),
                )
            )
        except Exception as e:
            logger.error(f"Failed to trigger call for {candidate_id}: {e}")
            call_session = CallSession(
                candidate_id=candidate.id,
                status="failed",
                external_call_id=None,
            )
            session.add(call_session)
            session.commit()
            raise self.retry(exc=e, countdown=30)

        # Create the call session record
        call_session = CallSession(
            candidate_id=candidate.id,
            external_call_id=external_call_id,
            status="in_progress",
        )
        session.add(call_session)
        session.commit()

        logger.info(f"Hunar call created: candidate={candidate_id}, external_id={external_call_id}")
        return external_call_id


@celery_app.task(name="tasks.extract_transcript", bind=True, max_retries=3)
def extract_transcript(self, call_session_id: str) -> bool:
    """
    Celery task: Extract answers + score from a completed call transcript or Hunar result.

    Flow:
    1. Load the CallSession (which has the transcript/results from the webhook)
    2. Load the Job to get the screening questions and pass criteria
    3. Call Gemini LLM to extract answers and score
    4. Write Answer + Score records, set status=completed
    """
    with Session(engine) as session:
        call_session = session.get(CallSession, call_session_id)
        if not call_session:
            logger.error(f"CallSession {call_session_id} not found")
            return False

        candidate = session.get(Candidate, call_session.candidate_id)
        if not candidate:
            logger.error(f"Candidate {call_session.candidate_id} not found")
            return False

        job = session.get(Job, candidate.job_id)
        if not job:
            logger.error(f"Job {candidate.job_id} not found")
            return False

        # Format transcript data for LLM analysis
        transcript_raw = call_session.transcript
        if isinstance(transcript_raw, dict):
            # Check if Hunar sent a structured result dict
            messages = []
            for k, v in transcript_raw.items():
                messages.append({"speaker": k, "text": str(v)})
            transcript_messages = messages
        elif isinstance(transcript_raw, list):
            transcript_messages = transcript_raw
        else:
            transcript_messages = [{"speaker": "Call", "text": str(transcript_raw or "")}]

        script_data = job.script or {}
        questions = script_data.get("questions", [])
        if not questions and job.pass_criteria:
            questions = [job.pass_criteria]

        pass_criteria = job.pass_criteria or "General fitness for the role"

        llm_client = LLMClient()

        try:
            answers = asyncio.run(
                llm_client.extract_answers_from_transcript(transcript_messages, questions)
            )
            score_data = asyncio.run(
                llm_client.score_transcript(transcript_messages, pass_criteria)
            )
        except Exception as e:
            logger.error(f"LLM extraction failed for session {call_session_id}: {e}")
            raise self.retry(exc=e, countdown=60)

        # Save answers
        for ans in answers:
            answer_record = Answer(
                call_session_id=call_session.id,
                question=ans.get("question", ""),
                extracted_answer=ans.get("extracted_answer", ""),
                confidence=float(ans.get("confidence", 0.0)),
            )
            session.add(answer_record)

        # Save score
        score_record = Score(
            call_session_id=call_session.id,
            score=int(score_data.get("score", 0)),
            reasoning=score_data.get("reasoning", ""),
        )
        session.add(score_record)

        call_session.status = "completed"
        session.add(call_session)
        session.commit()

        logger.info(
            f"Extraction complete: session={call_session_id}, "
            f"score={score_data.get('score')}, answers={len(answers)}"
        )
        return True
