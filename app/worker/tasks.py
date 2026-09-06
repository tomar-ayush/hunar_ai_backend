import asyncio
import logging
from typing import Optional, Callable, Any
from sqlmodel import Session, select

from app.database import engine
from app.candidates.model import Candidate
from app.jobs.model import Job
from app.voice.service import VoiceAIClient

logger = logging.getLogger(__name__)


def _make_delay_wrapper(
    async_func: Callable[..., Any],
) -> Callable[..., Any]:
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
    4. Store the external_call_id in candidate.call_id
    """
    with Session(engine) as session:
        candidate = session.get(Candidate, candidate_id)
        if not candidate:
            logger.error(f"Candidate {candidate_id} not found")
            return None

        # Load the job to get context & custom data
        job = session.get(Job, candidate.job_id)
        if not job:
            logger.error(
                f"Job {candidate.job_id} not found for candidate {candidate_id}"
            )
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
            "job_title": job.title,
            "job_description": (job.jd_text or job.title).strip(),
            "company": "Hunar ai",
            "company_name": "Hunar ai",
            "recruiter_org": "Hunar ai",
            "candidate_name": candidate.name,
            "callee_name": candidate.name,
            "location": job.target_location
            or candidate.location
            or "Bengaluru / Remote",
            "candidate_headline": f"{candidate.title or 'Engineer'} at {candidate.company or 'Tech Company'}",
            "candidate_current_title": candidate.title
            or job.title
            or "Engineer",
            "jd_summary": (
                job.jd_text or job.title or "Role at Recruiter Portal"
            )[:500],
            "key_requirements": ", ".join(job.required_skills)
            if isinstance(job.required_skills, list)
            and job.required_skills
            else (
                job.experience_required
                or "Relevant engineering experience"
            ),
        }
        if isinstance(script_data.get("custom_data"), dict):
            custom_data.update(script_data["custom_data"])

        effective_agent_id = agent_id or job.agent_id
        logger.info(
            f"Triggering call for candidate={candidate_id} ({candidate.name}), "
            f"phone={target_phone}, agent_id={effective_agent_id}, "
            f"custom_data={custom_data}"
        )

        voice_client = VoiceAIClient()

        external_call_id = None
        for attempt in range(max_retries + 1):
            try:
                external_call_id = (
                    await voice_client.trigger_outbound_call(
                        candidate_phone=target_phone,
                        candidate_name=candidate.name,
                        agent_id=effective_agent_id,
                        custom_data=custom_data,
                        request_id=str(candidate.id),
                    )
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
                    logger.error(
                        f"All call trigger attempts failed for candidate {candidate_id}: {e}"
                    )
                    return None

        # Map candidate to call
        candidate.call_id = external_call_id
        session.add(candidate)
        session.commit()

        logger.info(
            f"Hunar call created: candidate={candidate_id}, external_id={external_call_id}"
        )
        return external_call_id


# Backward compatibility aliases for fixtures/code expecting .delay()
trigger_call.delay = _make_delay_wrapper(trigger_call)
