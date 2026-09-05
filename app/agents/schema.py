from typing import List, Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class LanguageEnum(str, Enum):
    ENGLISH = "ENGLISH"
    HINDI = "HINDI"
    TAMIL = "TAMIL"
    TELUGU = "TELUGU"
    KANNADA = "KANNADA"
    MARATHI = "MARATHI"
    MALAYALAM = "MALAYALAM"
    GUJARATI = "GUJARATI"
    BENGALI = "BENGALI"
    TURKISH = "TURKISH"
    ARABIC = "ARABIC"
    SPANISH = "SPANISH"


class VoicePersonaEnum(str, Enum):
    NEHA = "NEHA"
    ROY = "ROY"
    ZOE = "ZOE"
    SAM = "SAM"
    MIRA = "MIRA"
    EESHA = "EESHA"


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=64, description="Agent name (3-64 characters)")
    language: LanguageEnum = Field(default=LanguageEnum.ENGLISH, description="Language for the agent")
    voice_persona: VoicePersonaEnum = Field(default=VoicePersonaEnum.NEHA, description="Voice persona identifier")
    persona_name: Optional[str] = Field(None, description="Display name for the persona, used in the voice call")
    agent_prompt: str = Field(..., description="System prompt that defines the agent's behavior and conversation style")
    objective: str = Field(..., description="Business objective that guides the agent's responses")
    introduction: str = Field(..., description="Opening message when the call connects")
    result_prompt: str = Field(..., description="Instructions for generating structured results from the conversation")
    result_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON schema defining the structure of data to collect")

    model_config = ConfigDict(extra="allow")


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=64)
    language: Optional[LanguageEnum] = None
    voice_persona: Optional[VoicePersonaEnum] = None
    persona_name: Optional[str] = None
    agent_prompt: Optional[str] = None
    objective: Optional[str] = None
    introduction: Optional[str] = None
    result_prompt: Optional[str] = None
    result_schema: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")


class AgentListItem(BaseModel):
    id: str
    name: str
    voice_persona: str
    persona_name: Optional[str] = None
    voice_name: Optional[str] = None
    summary: Optional[str] = None
    status: str = "ACTIVE"
    logo: Optional[str] = None
    language: str
    custom_variables: List[str] = Field(default_factory=list)
    result_schema: Dict[str, Any] = Field(default_factory=dict)
    agent_code: Optional[str] = None
    result_variables: List[str] = Field(default_factory=list)
    required_variables: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class AgentDetail(AgentListItem):
    created_at: Optional[str] = None
    agent_prompt: Optional[str] = None
    introduction: Optional[str] = None
    objective: Optional[str] = None
    silence_response: Optional[str] = None
    conclusion: Optional[str] = None
    result_prompt: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class AgentListResponse(BaseModel):
    count: int
    next: Optional[str] = None
    previous: Optional[str] = None
    results: List[AgentListItem]

    model_config = ConfigDict(extra="allow")
