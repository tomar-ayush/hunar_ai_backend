import httpx
import hmac
import hashlib
import logging
from typing import Dict, Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class VoiceAIClient:
    """
    Hunar.AI Voice AI API client.

    Handles:
    - Creating/configuring a voice AI agent for a job's screening script
    - Triggering outbound calls to candidates
    - Verifying webhook signatures

    The Hunar API typically works as:
    1. POST /agents       → create/configure an AI agent with a script
    2. POST /calls        → trigger an outbound call using that agent
    3. Webhook callback   → Hunar POSTs transcript + recording back to us
    """

    def __init__(self):
        self.base_url = settings.HUNAR_BASE_URL
        self.api_key = settings.HUNAR_API_KEY
        self.webhook_secret = settings.HUNAR_WEBHOOK_SECRET
        self.timeout = 30
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def trigger_outbound_call(
        self,
        candidate_phone: str,
        candidate_name: str,
        script: Dict[str, Any],
        webhook_url: str = "",
    ) -> str:
        """
        Trigger an outbound voice call to a candidate via Hunar.AI.

        Args:
            candidate_phone: Phone number in E.164 format
            candidate_name: Candidate's name for the agent to use
            script: Dict containing screening questions and opening line
            webhook_url: URL where Hunar will POST the call results

        Returns:
            external_call_id from Hunar's API response
        """
        if not self.api_key:
            logger.warning("HUNAR_API_KEY not set — returning mock call ID")
            mock_id = f"hunar_mock_{candidate_phone[-4:]}"
            return mock_id

        # Build the agent prompt from the job's screening script
        questions = script.get("questions", [])
        opening_line = script.get("opening_line", f"Hello {candidate_name}, this is an AI assistant calling about a job opportunity.")

        questions_text = "\n".join(
            f"- {q}" for q in questions
        ) if questions else "- Tell me about your relevant experience."

        agent_prompt = (
            f"You are a professional HR screening assistant. "
            f"You are calling {candidate_name} for a preliminary screening call. "
            f"Start with this opening: \"{opening_line}\". "
            f"Then ask the following screening questions one by one, waiting for the candidate's response before proceeding:\n"
            f"{questions_text}\n\n"
            f"Be conversational and professional. After all questions are answered, "
            f"thank the candidate and end the call politely. "
            f"Keep the call under 5 minutes."
        )

        payload = {
            "phone_number": candidate_phone,
            "agent": {
                "prompt": agent_prompt,
                "first_message": opening_line,
                "language": "en",
            },
            "metadata": {
                "candidate_name": candidate_name,
            },
        }

        if webhook_url:
            payload["webhook_url"] = webhook_url

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/calls",
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                call_id = data.get("call_id") or data.get("id") or data.get("external_id", "")
                logger.info(f"Hunar call triggered: {call_id} → {candidate_phone}")
                return call_id

            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Hunar API error {e.response.status_code}: {e.response.text}"
                )
                raise
            except httpx.HTTPError as e:
                logger.error(f"Hunar HTTP error: {e}")
                raise

    @staticmethod
    def verify_webhook_signature(
        payload_body: bytes, signature: str, secret: str
    ) -> bool:
        """
        Verify the HMAC-SHA256 signature from Hunar's webhook callback.
        Returns True if the signature is valid.
        """
        if not secret:
            # No secret configured — skip verification (dev mode)
            return True

        expected = hmac.new(
            secret.encode("utf-8"),
            payload_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)
