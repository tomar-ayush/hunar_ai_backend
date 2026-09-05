import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from app.database import get_session
from app.auth.service import get_current_user
import uuid

from unittest.mock import patch

sqlite_file_name = "sqlite:///./test.db"
engine = create_engine(sqlite_file_name, connect_args={"check_same_thread": False})

def get_session_override():
    with Session(engine) as session:
        yield session

def mock_get_current_user():
    return {"id": uuid.uuid4()}

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

def test_sourcing_flow(client: TestClient):
    # 1. Create a job
    job_data = {
        "company_id": str(uuid.uuid4()),
        "title": "Software Engineer",
        "jd_text": "Need python skills",
        "script": {"q1": "test"},
        "pass_criteria": "Knows Python",
        "sourcing_mode": "auto"
    }
    resp_job = client.post("/jobs", json=job_data)
    assert resp_job.status_code == 200
    job_id = resp_job.json()["id"]

    # 2. Source candidates (mocking LLM and Search clients)
    with patch('app.jobs.router.LLMClient') as MockLLM, \
         patch('app.jobs.router.PeopleSearchClient') as MockSearch:
        
        mock_llm_inst = MockLLM.return_value
        mock_llm_inst.extract_filters_from_jd.return_value = {"targetTitle": "Dev", "skills": ["Python"], "location": "Remote"}
        
        mock_search_inst = MockSearch.return_value
        mock_search_inst.search_candidates.return_value = [{"name": "Jane Doe", "email": "jane@example.com", "phone": "555-0101"}]

        resp_source = client.post(f"/jobs/{job_id}/source")
        assert resp_source.status_code == 200
        preview = resp_source.json()["preview"]
        assert len(preview) == 1
        assert preview[0]["name"] == "Jane Doe"

    # 3. Approve candidates
    approve_data = {
        "candidates": [
            {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "555-0101",
                "source": "people_search_api",
                "consent_status": "pending",
                "job_id": job_id
            }
        ]
    }
    resp_approve = client.post(f"/jobs/{job_id}/candidates/approve", json=approve_data)
    assert resp_approve.status_code == 200

    # 4. Fetch the created candidate to get ID
    resp_list = client.get(f"/jobs/{job_id}/candidates")
    assert resp_list.status_code == 200
    cands = resp_list.json()
    assert len(cands) == 1
    cand_id = cands[0]["id"]

    # 5. Call candidate
    with patch('app.candidates.router.trigger_call.delay') as mock_task:
        resp_call = client.post(f"/candidates/{cand_id}/call")
        assert resp_call.status_code == 202
        assert mock_task.called
