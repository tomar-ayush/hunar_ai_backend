import base64
import hashlib
import hmac
import httpx
import logging
from typing import Dict, Any, List, Optional, Iterable

from app.config import settings

logger = logging.getLogger(__name__)


def compute_hunar_signature(*, api_key: str, request_body: bytes, timestamp: str) -> str:
    """
    Computes base64-encoded HMAC-SHA256 signature matching Hunar's official specification:
    message = f"{timestamp.strip()}.".encode("utf-8") + request_body
    """
    message = f"{timestamp.strip()}.".encode("utf-8") + request_body
    digest = hmac.new(api_key.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_hunar_webhook_signature(
    *,
    signature_header: Optional[str],
    timestamp_header: Optional[str],
    request_body: bytes,
    trusted_api_keys: Iterable[str],
) -> bool:
    """
    Validates X-Hunar-Signature header against trusted API keys.
    Returns True if any comma-separated signature matches any trusted API key.
    """
    if not (signature_header and signature_header.strip()):
        return False
    if not (timestamp_header and timestamp_header.strip()):
        return False

    timestamp = timestamp_header.strip()
    signatures = [s.strip() for s in signature_header.split(",") if s.strip()]

    for api_key in trusted_api_keys:
        if not api_key:
            continue
        computed = compute_hunar_signature(
            api_key=api_key,
            request_body=request_body,
            timestamp=timestamp,
        )
        for sig in signatures:
            if hmac.compare_digest(sig, computed):
                return True

    return False


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

    async def list_agents(self, page: int = 1, page_size: int = 20) -> List[Dict[str, Any]]:
        """List active agents for the organization."""
        if not self.api_key:
            logger.warning("HUNAR_API_KEY not set — returning mock agent")
            return [{"id": "mock-agent-uuid-001", "name": "Default HR Screening Agent", "status": "ACTIVE"}]

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
            return {"id": "mock-agent-uuid-001", "name": f"{job_title} Screening Agent"}

        questions_text = "\n".join(f"- {q}" for q in screening_questions) if screening_questions else "- Describe your relevant experience."
        intro = opening_line or f"Hello! Am I speaking with {{callee_name}}? I'm calling about the {job_title} role."

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
            logger.warning("HUNAR_API_KEY not set — returning mock call ID")
            return f"hunar_mock_{candidate_phone[-4:] if candidate_phone else '0000'}"

        # Resolve agent_id: parameter -> settings -> first existing agent
        resolved_agent_id = agent_id or settings.HUNAR_AGENT_ID
        if not resolved_agent_id:
            agents = await self.list_agents(page_size=5)
            if agents:
                resolved_agent_id = agents[0].get("id")
            else:
                raise ValueError("No Hunar agent found. Set HUNAR_AGENT_ID or create an agent first.")

        # Prepare payload matching official schema
        call_payload: Dict[str, Any] = {
            "agent_id": resolved_agent_id,
            "callee_name": candidate_name or "Candidate",
            "mobile_number": candidate_phone,
            "custom_data": custom_data or {},
        }

        if request_id:
            call_payload["request_id"] = str(request_id)

        # Configure webhooks if callback URL is available
        cb_url = callback_url or (f"{settings.HUNAR_CALLBACK_BASE_URL.rstrip('/')}/webhooks/voice-call" if settings.HUNAR_CALLBACK_BASE_URL else None)
        if cb_url:
            call_payload["callback_config"] = {
                "call_status_callback_url": cb_url,
                "call_recording_callback_url": cb_url,
                "call_result_callback_url": cb_url,
                "call_summary_callback_url": cb_url,
            }

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
                logger.info(f"Hunar call triggered successfully: id={call_id} to={candidate_phone}")
                return str(call_id)
            except httpx.HTTPStatusError as e:
                logger.error(f"Hunar call creation error {e.response.status_code}: {e.response.text}")
                raise
            except httpx.HTTPError as e:
                logger.error(f"Hunar HTTP error: {e}")
                raise

    @staticmethod
    def verify_webhook_signature(
        request_body: bytes,
        signature_header: Optional[str],
        timestamp_header: Optional[str],
        api_key: str,
    ) -> bool:
        """Validates incoming webhook request using organization API key."""
        if not api_key:
            return True
        return verify_hunar_webhook_signature(
            signature_header=signature_header,
            timestamp_header=timestamp_header,
            request_body=request_body,
            trusted_api_keys=[api_key],
        )
