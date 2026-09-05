import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from app.calls.model import CallSession
from app.database import get_session
from app.auth.service import get_current_user
from app.auth.model import User
import uuid
from unittest.mock import patch

sqlite_url = "sqlite:///./test_webhooks.db"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})


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
    """Verify that the webhook endpoint is idempotent by external_call_id."""
    ext_id = f"test-ext-{uuid.uuid4().hex[:8]}"

    # Insert a mock CallSession in in_progress state
    with Session(engine) as session:
        call = CallSession(
            candidate_id=uuid.uuid4(),
            status="in_progress",
            external_call_id=ext_id,
        )
        session.add(call)
        session.commit()
        session.refresh(call)

    payload = {
        "external_call_id": ext_id,
        "status": "completed",
        "transcript": [{"speaker": "AI", "text": "Hello"}, {"speaker": "Candidate", "text": "Hi"}],
        "recording_url": "https://example.com/rec.mp3",
        "duration": 180,
    }

    with patch("app.webhooks.router.extract_transcript") as mock_task:
        mock_task.delay = lambda *a, **k: None

        # First call should succeed
        resp1 = client.post("/webhooks/voice-call", json=payload)
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "success"

        # Second call should be ignored (idempotent)
        resp2 = client.post("/webhooks/voice-call", json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ignored"
        assert resp2.json()["detail"] == "already processed"


def test_webhook_unknown_call_id(client: TestClient):
    """Webhook should ignore payloads with unknown external_call_id."""
    payload = {
        "external_call_id": "nonexistent-id",
        "status": "completed",
        "transcript": [],
    }
    resp = client.post("/webhooks/voice-call", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert resp.json()["detail"] == "session not found"
