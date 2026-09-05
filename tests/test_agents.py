import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from app.database import get_session
from app.auth.service import get_current_user
from app.auth.model import User
import uuid

sqlite_url = "sqlite:///./test_agents.db"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})


def get_session_override():
    with Session(engine) as session:
        yield session


def mock_get_current_user():
    return User(
        id=uuid.uuid4(),
        company_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        email="recruiter@example.com",
        hashed_password="fake",
    )


@pytest.fixture(name="client")
def client_fixture():
    from main import app

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = mock_get_current_user
    SQLModel.metadata.create_all(engine)
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
    SQLModel.metadata.drop_all(engine)


def test_list_agents(client: TestClient):
    """Test listing agents."""
    resp = client.get("/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "count" in data
    assert len(data["results"]) >= 1
    agent = data["results"][0]
    assert agent["voice_persona"] == "NEHA"


def test_create_and_get_agent(client: TestClient):
    """Test creating a new agent and retrieving its details."""
    payload = {
        "name": "Frontend Screening Agent",
        "language": "ENGLISH",
        "voice_persona": "ROY",
        "persona_name": "Roy",
        "agent_prompt": "You are screening Senior React Engineers.",
        "objective": "Screen candidate technical proficiency.",
        "introduction": "Hi {callee_name}, calling from {company} about {job_role}.",
        "result_prompt": "Extract React expertise and salary expectation.",
        "result_schema": {
            "react_experience_years": "number",
            "qualified": "boolean"
        }
    }

    create_resp = client.post("/agents", json=payload)
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["name"] == "Frontend Screening Agent"
    assert created["voice_persona"] == "ROY"
    agent_id = created["id"]

    # Retrieve details
    detail_resp = client.get(f"/agents/{agent_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["id"] == agent_id
    assert detail["name"] == "Frontend Screening Agent"


def test_update_agent(client: TestClient):
    """Test updating agent settings."""
    # Create first
    payload = {
        "name": "DevOps Agent",
        "language": "ENGLISH",
        "voice_persona": "ZOE",
        "persona_name": "Zoe",
        "agent_prompt": "You are screening DevOps Engineers.",
        "objective": "Screen candidate Kubernetes proficiency.",
        "introduction": "Hello {callee_name}!",
        "result_prompt": "Extract Kubernetes experience.",
        "result_schema": {"k8s": "boolean"}
    }
    create_resp = client.post("/agents", json=payload)
    agent_id = create_resp.json()["id"]

    # Update
    update_payload = {
        "name": "Senior DevOps Screener",
        "objective": "Updated objective: screen senior candidates.",
    }
    update_resp = client.put(f"/agents/{agent_id}", json=update_payload)
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["name"] == "Senior DevOps Screener"
