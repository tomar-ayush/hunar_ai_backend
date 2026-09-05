import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from app.database import get_session
from app.auth.service import get_current_user
from app.auth.model import User
import uuid
from unittest.mock import patch, MagicMock, AsyncMock

sqlite_url = "sqlite:///./test_sourcing.db"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})


def get_session_override():
    with Session(engine) as session:
        yield session


# Return a proper User-like object instead of a dict
def mock_get_current_user():
    user = User(
        id=uuid.uuid4(),
        company_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        email="test@example.com",
        hashed_password="fake",
    )
    return user


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


def test_full_sourcing_flow(client: TestClient):
    """
    End-to-end test: Create Job → Source Candidates → Approve → Trigger Call.
    """
    company_id = "00000000-0000-0000-0000-000000000001"

    # 1. Create a job
    job_data = {
        "company_id": company_id,
        "title": "Senior Backend Engineer",
        "jd_text": "We need a Python backend engineer with 5+ years experience in FastAPI and PostgreSQL.",
        "script": {
            "questions": [
                "Tell me about your experience with FastAPI.",
                "How do you handle database migrations?",
            ],
            "opening_line": "Hi, I'm calling about the Backend Engineer position.",
        },
        "pass_criteria": "Must have 5+ years Python experience. Must know FastAPI and PostgreSQL.",
        "sourcing_mode": "auto",
    }
    resp_job = client.post("/jobs", json=job_data)
    assert resp_job.status_code == 200, resp_job.text
    job_id = resp_job.json()["id"]

    # 2. Source candidates (mock LLM + Apollo clients)
    with patch("app.jobs.router.LLMClient") as MockLLM, \
         patch("app.jobs.router.PeopleSearchClient") as MockSearch:

        mock_llm_inst = MockLLM.return_value
        mock_llm_inst.extract_filters_from_jd = MagicMock(
            return_value={
                "targetTitle": "Backend Engineer",
                "skills": ["Python", "FastAPI"],
                "location": "Remote",
            }
        )
        # Make it awaitable
        import asyncio
        mock_llm_inst.extract_filters_from_jd = lambda *a, **k: asyncio.coroutine(
            lambda: {"targetTitle": "Backend Engineer", "skills": ["Python", "FastAPI"], "location": "Remote"}
        )()

        mock_search_inst = MockSearch.return_value
        mock_search_inst.search_candidates = lambda *a, **k: asyncio.coroutine(
            lambda: [
                {"name": "Priya Sharma", "email": "priya@example.com", "phone": "+91-9876543210"}
            ]
        )()

        resp_source = client.post(f"/jobs/{job_id}/source")
        assert resp_source.status_code == 200, resp_source.text
        preview = resp_source.json()["preview"]
        assert len(preview) == 1
        assert preview[0]["name"] == "Priya Sharma"

    # 3. Approve candidates
    approve_data = {
        "candidates": [
            {
                "name": "Priya Sharma",
                "email": "priya@example.com",
                "phone": "+91-9876543210",
                "source": "people_search_api",
                "consent_status": "granted",
                "job_id": job_id,
            }
        ]
    }
    resp_approve = client.post(f"/jobs/{job_id}/candidates/approve", json=approve_data)
    assert resp_approve.status_code == 200
    assert resp_approve.json()["count"] == 1

    # 4. List candidates
    resp_list = client.get(f"/jobs/{job_id}/candidates")
    assert resp_list.status_code == 200
    cands = resp_list.json()
    assert len(cands) == 1
    cand_id = cands[0]["id"]

    # 5. Trigger a call (mock Celery task)
    with patch("app.candidates.router.trigger_call") as mock_task:
        mock_task.delay = MagicMock()
        resp_call = client.post(f"/candidates/{cand_id}/call")
        assert resp_call.status_code == 202
        mock_task.delay.assert_called_once_with(cand_id)

    # 6. Check dashboard
    resp_dash = client.get(f"/jobs/{job_id}/dashboard")
    assert resp_dash.status_code == 200
    dashboard = resp_dash.json()
    assert dashboard["total_candidates"] == 1
    assert dashboard["dashboard"][0]["candidate"]["name"] == "Priya Sharma"
    assert dashboard["dashboard"][0]["call_status"] == "not_called"


def test_csv_upload(client: TestClient):
    """Test CSV candidate upload."""
    company_id = "00000000-0000-0000-0000-000000000001"

    # Create a job first
    job_data = {
        "company_id": company_id,
        "title": "QA Engineer",
        "jd_text": "QA role",
        "script": {},
        "pass_criteria": "Manual testing experience",
        "sourcing_mode": "manual",
    }
    resp_job = client.post("/jobs", json=job_data)
    job_id = resp_job.json()["id"]

    # Upload CSV
    csv_content = "name,phone,email\nAlice Johnson,+1-555-0101,alice@test.com\nBob Lee,+1-555-0102,bob@test.com\n"
    resp = client.post(
        f"/jobs/{job_id}/candidates/csv",
        files={"file": ("candidates.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 200
    assert resp.json()["imported"] == 2

    # Verify candidates were created
    resp_list = client.get(f"/jobs/{job_id}/candidates")
    assert len(resp_list.json()) == 2
