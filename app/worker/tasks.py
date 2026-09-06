import asyncio
import logging
from typing import Optional, Callable, Any
from sqlmodel import Session, select

from app.database import engine
from app.candidates.model import Candidate
from app.jobs.model import Job
from app.calls.model import CallSession, Answer, Score
from app.voice.service import VoiceAIClient
from app.llm.service import LLMClient

logger = logging.getLogger(__name__)


def _make_delay_wrapper(async_func: Callable[..., Any]) -> Callable[..., Any]:
    """Provides backward compatibility for code or test fixtures invoking .delay()."""
    def delay(*args, **kwargs):
        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(async_func(*args, **kwargs))
        except RuntimeError:
            return asyncio.run(async_func(*args, **kwargs))
    return delay


async def trigger_call(
    candidate_id: str,
    agent_id: Optional[str] = None,
    phone_number: Optional[str] = None,
    max_retries: int = 2,
) -> Optional[str]:
    """
    FastAPI Background Task: Trigger an outbound voice call via Hunar.AI.

    Flow:
    1. Load candidate + job from DB
    2. Build custom_data & resolve agent (using optional agent_id override)
    3. Call Hunar.AI Voice API (POST /external/v1/calls/) with target phone number
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

        # Resolve target phone number: override if provided, else candidate's phone
        target_phone = (phone_number or candidate.phone or "").strip()
        if phone_number and candidate.phone != phone_number:
            candidate.phone = phone_number
            session.add(candidate)
            session.commit()
            session.refresh(candidate)

        script_data = job.script or {}
        custom_data = {
            "job_role": job.title,
            "company": "Recruiter Portal",
            "candidate_name": candidate.name,
        }
        if isinstance(script_data.get("custom_data"), dict):
            custom_data.update(script_data["custom_data"])

        voice_client = VoiceAIClient()

        external_call_id = None
        for attempt in range(max_retries + 1):
            try:
                external_call_id = await voice_client.trigger_outbound_call(
                    candidate_phone=target_phone,
                    candidate_name=candidate.name,
                    agent_id=agent_id,
                    custom_data=custom_data,
                    request_id=str(candidate.id),
                )
                if external_call_id:
                    break
            except Exception as e:
                logger.warning(
                    f"Call trigger attempt {attempt + 1}/{max_retries + 1} failed for {candidate_id}: {e}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(2 * (attempt + 1))
                else:
                    logger.error(f"All call trigger attempts failed for candidate {candidate_id}: {e}")
                    call_session = CallSession(
                        candidate_id=candidate.id,
                        status="failed",
                        external_call_id=None,
                    )
                    session.add(call_session)
                    session.commit()
                    return None

        # Map candidate to call
        candidate.call_id = external_call_id
        session.add(candidate)

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


async def extract_transcript(call_session_id: str, max_retries: int = 2) -> bool:
    """
    FastAPI Background Task: Extract answers + score from a completed call transcript or Hunar result.

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

        # Format transcript data
        transcript_raw = call_session.transcript

        # If Hunar already provided evaluated results (questions, answers, suitability score)
        if isinstance(transcript_raw, dict) and any(k.startswith("question_") for k in transcript_raw.keys()):
            script_data = job.script or {}
            job_questions = script_data.get("questions", [])

            # Save answers
            for k, val in transcript_raw.items():
                if k.startswith("question_") and k.endswith("_answer"):
                    try:
                        idx = int(k.split("_")[1]) - 1
                        q_text = job_questions[idx] if 0 <= idx < len(job_questions) else k.replace("_", " ").title()
                    except (ValueError, IndexError):
                        q_text = k.replace("_", " ").title()

                    session.add(
                        Answer(
                            call_session_id=call_session.id,
                            question=q_text,
                            extracted_answer=str(val),
                            confidence=1.0,
                        )
                    )

            # Save score
            suitability = transcript_raw.get("suitability_score")
            score_val = 70
            if suitability is not None:
                try:
                    s_float = float(suitability)
                    score_val = int(s_float * 10) if s_float <= 10 else int(s_float)
                except ValueError:
                    pass

            summary = transcript_raw.get("candidate_summary", "")
            rec = transcript_raw.get("overall_recommendation", "")
            reasoning_parts = [p for p in [summary, f"Recommendation: {rec}" if rec else ""] if p]
            reasoning = " | ".join(reasoning_parts) or "Evaluated by Hunar Voice AI"

            session.add(
                Score(
                    call_session_id=call_session.id,
                    score=score_val,
                    reasoning=reasoning,
                )
            )

            call_session.status = "completed"
            session.add(call_session)
            session.commit()
            logger.info(f"Extraction complete directly from Hunar result: session={call_session_id}, score={score_val}")
            return True

        if isinstance(transcript_raw, dict):
            messages = [{"speaker": k, "text": str(v)} for k, v in transcript_raw.items()]
            transcript_messages = messages
        elif isinstance(transcript_raw, list):
            transcript_messages = transcript_raw
        else:
            transcript_messages = [{"speaker": "Call", "text": str(transcript_raw or "")}]

        script_data = job.script or {}
        questions = script_data.get("questions", [])

        skills_str = ", ".join(job.required_skills) if isinstance(job.required_skills, list) else str(job.required_skills or "")
        scoring_criteria = (
            f"Role: {job.title}. "
            f"Seniority: {job.target_seniority_level or 'Not specified'}. "
            f"Experience Required: {job.experience_required or 'Not specified'}. "
            f"Required Skills: {skills_str or 'General competency'}."
        )

        llm_client = LLMClient()

        answers = []
        score_data = {}
        for attempt in range(max_retries + 1):
            try:
                answers = await llm_client.extract_answers_from_transcript(transcript_messages, questions)
                score_data = await llm_client.score_transcript(transcript_messages, scoring_criteria)
                break
            except Exception as e:
                logger.warning(
                    f"LLM extraction attempt {attempt + 1}/{max_retries + 1} failed for session {call_session_id}: {e}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(3 * (attempt + 1))
                else:
                    logger.error(f"All LLM extraction attempts failed for session {call_session_id}: {e}")
                    return False

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


# Backward compatibility aliases for fixtures/code expecting .delay()
trigger_call.delay = _make_delay_wrapper(trigger_call)
extract_transcript.delay = _make_delay_wrapper(extract_transcript)
