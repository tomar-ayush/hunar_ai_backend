import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class VoiceAIClient:
    def __init__(self, base_url: str = "https://api.voiceai.mock", timeout: int = 10):
        self.base_url = base_url
        self.timeout = timeout

    async def trigger_outbound_call(self, candidate_phone: str, script: Dict[str, Any]) -> str:
        """
        Trigger an outbound call using the Voice AI provider.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # In a real scenario:
                # response = await client.post(
                #     f"{self.base_url}/calls",
                #     json={"phone": candidate_phone, "script": script}
                # )
                # response.raise_for_status()
                # return response.json().get("call_id")
                
                # Mocked response
                logger.info(f"Triggering mock call to {candidate_phone} with script {script}")
                mock_call_id = f"ext_call_{candidate_phone[-4:] if candidate_phone else 'mock'}"
                return mock_call_id
            except httpx.HTTPError as e:
                logger.error(f"HTTP error occurred while triggering call: {e}")
                raise
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
                raise
