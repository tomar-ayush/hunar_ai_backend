import json
import httpx
import logging
from typing import Dict, Any, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class VoiceAIClient:
    """
    Official Hunar.AI Voice API Client (https://api.voice.hunar.ai/external/v1/).

    Authentication:
        All requests require 'X-API-Key: <HUNAR_API_KEY>' in headers.
        Webhook validation uses the same API key (no separate secret).

    Endpoints:
        - GET  /agents/              -> List organization voice agents
        - POST /agents/              -> Create a new agent
        - POST /calls/               -> Trigger an outbound call
        - GET  /calls/{call_id}/     -> Get call details & status
    """

    def __init__(self):
        self.base_url = settings.HUNAR_BASE_URL.rstrip("/")
        self.api_key = settings.HUNAR_API_KEY
        self.timeout = 30
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def list_agents(
        self, page: int = 1, page_size: int = 20
    ) -> List[Dict[str, Any]]:
        """List active agents for the organization."""
        if not self.api_key:
            logger.warning(
                "HUNAR_API_KEY not set — returning mock agent"
            )
            return [
                {
                    "id": "mock-agent-uuid-001",
                    "name": "Default HR Screening Agent",
                    "status": "ACTIVE",
                }
            ]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/agents/",
                    headers=self.headers,
                    params={"page": page, "page_size": page_size},
                )
                response.raise_for_status()
                data = response.json()
                return data.get("results", [])
            except httpx.HTTPError as e:
                logger.error(f"Failed to list Hunar agents: {e}")
                raise

    async def create_screening_agent(
        self,
        job_title: str,
        screening_questions: List[str],
        opening_line: str = "",
    ) -> Dict[str, Any]:
        """Create a dedicated screening agent configured for a specific job."""
        if not self.api_key:
            return {
                "id": "mock-agent-uuid-001",
                "name": f"{job_title} Screening Agent",
            }

        questions_text = (
            "\n".join(f"- {q}" for q in screening_questions)
            if screening_questions
            else "- Describe your relevant experience."
        )
        intro = (
            opening_line
            or f"Hello! Am I speaking with {{callee_name}}? I'm calling about the {job_title} role."
        )

        agent_data = {
            "name": f"{job_title[:40]} Screening Agent",
            "language": "ENGLISH",
            "voice_persona": "NEHA",
            "persona_name": "Neha",
            "agent_prompt": (
                f"You are a professional HR recruiter screening candidates for the {job_title} position. "
                f"Conduct a warm, structured interview asking these questions one by one:\n{questions_text}\n"
                f"Listen carefully to the candidate and ask follow-ups if their answers are brief. "
                f"Thank the candidate politely before concluding."
            ),
            "objective": f"Screen candidate suitability and interest for {job_title}.",
            "introduction": intro,
            "result_prompt": "Extract candidate answers, qualification status, and overall interest from this conversation.",
            "result_schema": {
                "interested": "boolean",
                "qualified": "boolean",
                "key_skills_demonstrated": "string",
                "summary": "string",
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/agents/",
                    headers=self.headers,
                    json=agent_data,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Failed to create Hunar agent: {e}")
                raise

    async def trigger_outbound_call(
        self,
        candidate_phone: str,
        candidate_name: str,
        agent_id: Optional[str] = None,
        custom_data: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        callback_url: Optional[str] = None,
    ) -> str:
        """
        Trigger an outbound call using Hunar Voice Agents API.

        Endpoint: POST /external/v1/calls/
        """
        if not self.api_key:
            logger.warning(
                "HUNAR_API_KEY not set — returning mock call ID"
            )
            return f"hunar_mock_{candidate_phone[-4:] if candidate_phone else '0000'}"

        # Resolve agent_id: parameter -> settings -> first existing agent
        resolved_agent_id = agent_id or settings.HUNAR_AGENT_ID
        if not resolved_agent_id:
            raise ValueError(
                "No Hunar agent set. Set HUNAR_AGENT_ID or create an agent first."
            )

        # Ensure phone number is E.164 formatted
        formatted_phone = (
            candidate_phone.strip() if candidate_phone else ""
        )
        if formatted_phone and not formatted_phone.startswith("+"):
            if len(formatted_phone) == 10:
                formatted_phone = f"+91{formatted_phone}"
            else:
                formatted_phone = f"+{formatted_phone}"

        # Ensure standard keys expected by agents are always populated
        merged_custom_data = {
            "job_role": "Software Engineer",
            "job_title": "Software Engineer",
            "job_description": "Role at Recruiter Portal",
            "company": "Recruiter Portal",
            "company_name": "Recruiter Portal",
            "recruiter_org": "Recruiter Portal",
            "candidate_name": candidate_name or "Candidate",
            "callee_name": candidate_name or "Candidate",
            "location": "Bengaluru / Remote",
            "candidate_headline": "Candidate",
            "candidate_current_title": "Engineer",
            "jd_summary": "Role at Recruiter Portal",
            "key_requirements": "Relevant experience",
        }
        if custom_data:
            merged_custom_data.update(custom_data)

        # Prepare payload matching official schema
        call_payload: Dict[str, Any] = {
            "agent_id": resolved_agent_id,
            "callee_name": candidate_name or "Candidate",
            "mobile_number": formatted_phone,
            "custom_data": merged_custom_data,
        }

        if request_id:
            call_payload["request_id"] = str(request_id)

        # Configure webhooks if callback URL is available
        cb_url = callback_url or (
            f"{settings.HUNAR_CALLBACK_BASE_URL.rstrip('/')}/webhooks/voice-call"
            if settings.HUNAR_CALLBACK_BASE_URL
            else None
        )
        if cb_url:
            call_payload["callback_config"] = {
                "call_status_callback_url": cb_url,
                "call_recording_callback_url": cb_url,
                "call_result_callback_url": cb_url,
                "call_summary_callback_url": cb_url,
            }

        logger.info(
            f"Sending outbound call request to Hunar API: url={self.base_url}/calls/, payload={json.dumps(call_payload, default=str)}"
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/calls/",
                    headers=self.headers,
                    json=call_payload,
                )
                response.raise_for_status()
                data = response.json()
                call_id = data.get("id")
                logger.info(
                    f"Hunar call triggered successfully: id={call_id} to={candidate_phone}, response={data}"
                )
                return str(call_id)
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Hunar call creation error {e.response.status_code}: response_text={e.response.text}, payload_sent={call_payload}"
                )
                raise
            except httpx.HTTPError as e:
                logger.error(f"Hunar HTTP error: {e}, payload_sent={call_payload}")
                raise

    async def get_call_details(self, call_id: str) -> Dict[str, Any]:
        """
        Fetch full call details and extracted results from Hunar Voice API.
        Endpoint: GET /external/v1/calls/{call_id}/
        """
        if not self.api_key:
            logger.warning("HUNAR_API_KEY not set — cannot fetch call details")
            return {}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/calls/{call_id}/",
                    headers=self.headers,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Failed to fetch Hunar call details for {call_id}: {e}")
                raise
