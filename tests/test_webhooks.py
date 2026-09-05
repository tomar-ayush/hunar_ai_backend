import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from app.calls.model import CallSession
from app.database import get_session
import uuid

# Mock the celery task
from unittest.mock import patch
import app.webhooks.router

# Setup test DB
sqlite_file_name = "sqlite:///./test.db"
engine = create_engine(sqlite_file_name, connect_args={"check_same_thread": False})

def get_session_override():
    with Session(engine) as session:
        yield session

@pytest.fixture(name="client")
def client_fixture():
    from main import app
    app.dependency_overrides[get_session] = get_session_override
    SQLModel.metadata.create_all(engine)
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
    SQLModel.metadata.drop_all(engine)

def test_webhook_idempotency(client: TestClient):
    # Insert a mock CallSession
    ext_id = "test-ext-123"
    with Session(engine) as session:
        call = CallSession(
            candidate_id=uuid.uuid4(),
            status="in_progress",
            external_call_id=ext_id
        )
        session.add(call)
        session.commit()
        session.refresh(call)

    payload = {
        "external_call_id": ext_id,
        "status": "completed",
        "transcript": {"hello": "world"},
        "recording_url": "http://example.com/rec.mp3"
    }

    with patch('app.webhooks.router.extract_transcript.delay') as mock_task:
        # First call should succeed and enqueue task
        resp1 = client.post("/webhooks/voice-call", json=payload)
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "success"
        assert mock_task.called

        mock_task.reset_mock()

        # Second call should be ignored due to idempotency
        resp2 = client.post("/webhooks/voice-call", json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ignored"
        assert not mock_task.called
