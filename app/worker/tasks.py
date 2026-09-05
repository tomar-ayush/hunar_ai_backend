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
    2. Build the screening script from the Job's questions
    3. Call Hunar.AI Voice API
    4. Store the external_call_id, set status=in_progress
    """
    with Session(engine) as session:
        candidate = session.get(Candidate, candidate_id)
        if not candidate:
            logger.error(f"Candidate {candidate_id} not found")
            return None

        # Load the job to get the screening script
        job = session.get(Job, candidate.job_id)
        if not job:
            logger.error(f"Job {candidate.job_id} not found for candidate {candidate_id}")
            return None

        # Build the script payload from the job
        script_data = job.script or {}
        script = {
            "questions": script_data.get("questions", job.pass_criteria.split(". ") if job.pass_criteria else []),
            "opening_line": script_data.get("opening_line", f"Hello {candidate.name}, I'm calling regarding the {job.title} position."),
        }

        voice_client = VoiceAIClient()

        try:
            external_call_id = asyncio.run(
                voice_client.trigger_outbound_call(
                    candidate_phone=candidate.phone,
                    candidate_name=candidate.name,
                    script=script,
                )
            )
        except Exception as e:
            logger.error(f"Failed to trigger call for {candidate_id}: {e}")
            # Create a failed session
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

        logger.info(f"Call triggered: candidate={candidate_id}, external_id={external_call_id}")
        return external_call_id


@celery_app.task(name="tasks.extract_transcript", bind=True, max_retries=3)
def extract_transcript(self, call_session_id: str) -> bool:
    """
    Celery task: Extract answers + score from a completed call transcript.

    Flow:
    1. Load the CallSession (which now has the transcript from the webhook)
    2. Load the Job to get the screening questions and pass criteria
    3. Call Gemini LLM to extract answers
    4. Call Gemini LLM to score the transcript
    5. Write Answer + Score records, set status=completed
    """
    with Session(engine) as session:
        call_session = session.get(CallSession, call_session_id)
        if not call_session:
            logger.error(f"CallSession {call_session_id} not found")
            return False

        # Get the candidate to find the job
        candidate = session.get(Candidate, call_session.candidate_id)
        if not candidate:
            logger.error(f"Candidate {call_session.candidate_id} not found")
            return False

        job = session.get(Job, candidate.job_id)
        if not job:
            logger.error(f"Job {candidate.job_id} not found")
            return False

        # Parse the transcript — Hunar typically sends a list of messages
        transcript = call_session.transcript
        if isinstance(transcript, dict):
            # Handle different transcript formats from Hunar
            transcript_messages = transcript.get("messages", [])
            if not transcript_messages:
                # Try to convert the dict itself to a list
                transcript_messages = [transcript]
        elif isinstance(transcript, list):
            transcript_messages = transcript
        else:
            transcript_messages = []

        # Get the screening questions from the job
        script_data = job.script or {}
        questions = script_data.get("questions", [])
        if not questions and job.pass_criteria:
            questions = [job.pass_criteria]

        pass_criteria = job.pass_criteria or "General fitness for the role"

        llm_client = LLMClient()

        try:
            # Extract answers from transcript
            answers = asyncio.run(
                llm_client.extract_answers_from_transcript(transcript_messages, questions)
            )

            # Score the transcript
            score_data = asyncio.run(
                llm_client.score_transcript(transcript_messages, pass_criteria)
            )
        except Exception as e:
            logger.error(f"LLM extraction failed for session {call_session_id}: {e}")
            raise self.retry(exc=e, countdown=60)

        # Write Answer records
        for ans in answers:
            answer_record = Answer(
                call_session_id=call_session.id,
                question=ans.get("question", ""),
                extracted_answer=ans.get("extracted_answer", ""),
                confidence=float(ans.get("confidence", 0.0)),
            )
            session.add(answer_record)

        # Write Score record
        score_record = Score(
            call_session_id=call_session.id,
            score=int(score_data.get("score", 0)),
            reasoning=score_data.get("reasoning", ""),
        )
        session.add(score_record)

        # Mark session as completed
        call_session.status = "completed"
        session.add(call_session)
        session.commit()

        logger.info(
            f"Extraction complete: session={call_session_id}, "
            f"score={score_data.get('score')}, answers={len(answers)}"
        )
        return True
