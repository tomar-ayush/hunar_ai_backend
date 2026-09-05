import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, status

from app.agents.schema import AgentCreate, AgentUpdate, AgentListResponse, AgentDetail
from app.agents.service import HunarAgentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["Hunar Voice Agents"])


@router.get("", response_model=AgentListResponse)
@router.get("/", response_model=AgentListResponse, include_in_schema=False)
async def list_agents(
    language: Optional[str] = Query(None, description="Filter by language (e.g. ENGLISH, HINDI)"),
    voice_persona: Optional[str] = Query(None, description="Filter by voice persona (e.g. NEHA, ROY, ZOE, SAM, MIRA, EESHA)"),
    agent_status: Optional[str] = Query(None, alias="status", description="Filter by status (e.g. ACTIVE, DRAFT)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """
    1. List Voice Agents
    Retrieve all voice agents for your organization with optional filtering and pagination.
    Calls Hunar Voice API: GET /external/v1/agents/
    """
    service = HunarAgentService()
    try:
        data = await service.list_agents(
            language=language,
            voice_persona=voice_persona,
            status=agent_status,
            page=page,
            page_size=page_size,
        )
        return data
    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_id}", response_model=AgentDetail)
@router.get("/{agent_id}/", response_model=AgentDetail, include_in_schema=False)
async def get_agent_details(
    agent_id: str,
):
    """
    2. Get Agent Details
    Retrieve detailed configuration, system prompts, introduction, and result schema for a specific agent.
    Calls Hunar Voice API: GET /external/v1/agents/{agent_id}/
    """
    service = HunarAgentService()
    try:
        agent = await service.get_agent(agent_id=agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=AgentDetail, status_code=status.HTTP_200_OK)
@router.post("/", response_model=AgentDetail, status_code=status.HTTP_200_OK, include_in_schema=False)
async def create_agent(
    payload: AgentCreate,
):
    """
    3. Create Agent
    Create a new AI voice agent for outbound calls.
    Calls Hunar Voice API: POST /external/v1/agents/
    """
    service = HunarAgentService()
    try:
        created = await service.create_agent(payload=payload)
        return created
    except Exception as e:
        logger.error(f"Error creating agent: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{agent_id}", response_model=Dict[str, Any])
@router.put("/{agent_id}/", response_model=Dict[str, Any], include_in_schema=False)
async def update_agent(
    agent_id: str,
    payload: AgentUpdate,
):
    """
    4. Update Agent
    Update and modify existing AI voice agent parameters, prompts, or schema.
    Calls Hunar Voice API: PUT /external/v1/agents/{agent_id}/
    """
    service = HunarAgentService()
    try:
        updated = await service.update_agent(agent_id=agent_id, payload=payload)
        return updated
    except Exception as e:
        logger.error(f"Error updating agent {agent_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
