import httpx
import logging
from typing import Dict, Any, Optional

from app.config import settings
from app.agents.schema import AgentCreate, AgentUpdate

logger = logging.getLogger(__name__)


class HunarAgentService:
    """
    Service client for Hunar.AI Voice Agents API:
    - GET  /agents/          -> List agents with filters and pagination
    - GET  /agents/{id}/     -> Get agent details
    - POST /agents/          -> Create new agent
    - PUT  /agents/{id}/     -> Update existing agent
    """

    def __init__(self):
        self.base_url = settings.HUNAR_BASE_URL.rstrip("/")
        self.api_key = settings.HUNAR_API_KEY
        self.timeout = 30.0

    def _get_headers(self) -> Dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def list_agents(
        self,
        language: Optional[str] = None,
        voice_persona: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """Fetch list of agents from Hunar Voice API."""
        params: Dict[str, Any] = {"page": page, "page_size": page_size}
        if language:
            params["language"] = language
        if voice_persona:
            params["voice_persona"] = voice_persona
        if status:
            params["status"] = status

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/agents/",
                    headers=self._get_headers(),
                    params=params,
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Hunar List Agents error {e.response.status_code}: {e.response.text}")
                raise
            except httpx.HTTPError as e:
                logger.error(f"Hunar network error: {e}")
                raise

    async def get_agent(self, agent_id: str) -> Dict[str, Any]:
        """Fetch detailed information about a specific agent."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/agents/{agent_id}/",
                    headers=self._get_headers(),
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Hunar Get Agent error {e.response.status_code}: {e.response.text}")
                raise
            except httpx.HTTPError as e:
                logger.error(f"Hunar network error: {e}")
                raise

    async def create_agent(self, payload: AgentCreate) -> Dict[str, Any]:
        """Create a new agent via Hunar Voice API."""
        data = payload.model_dump(exclude_none=True)
        # Ensure enum values are serialized to strings
        if "language" in data and hasattr(data["language"], "value"):
            data["language"] = data["language"].value
        if "voice_persona" in data and hasattr(data["voice_persona"], "value"):
            data["voice_persona"] = data["voice_persona"].value

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/agents/",
                    headers=self._get_headers(),
                    json=data,
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Hunar Create Agent error {e.response.status_code}: {e.response.text}")
                raise
            except httpx.HTTPError as e:
                logger.error(f"Hunar network error: {e}")
                raise

    async def update_agent(self, agent_id: str, payload: AgentUpdate) -> Dict[str, Any]:
        """Update an existing agent via Hunar Voice API."""
        data = payload.model_dump(exclude_none=True)
        if "language" in data and hasattr(data["language"], "value"):
            data["language"] = data["language"].value
        if "voice_persona" in data and hasattr(data["voice_persona"], "value"):
            data["voice_persona"] = data["voice_persona"].value

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.put(
                    f"{self.base_url}/agents/{agent_id}/",
                    headers=self._get_headers(),
                    json=data,
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Hunar Update Agent error {e.response.status_code}: {e.response.text}")
                raise
            except httpx.HTTPError as e:
                logger.error(f"Hunar network error: {e}")
                raise
