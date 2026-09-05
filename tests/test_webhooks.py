import json
import pytest
import time
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from app.calls.model import CallSession
from app.database import get_session
from app.voice.service import compute_hunar_signature
from app.config import settings
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


def test_hunar_webhook_idempotency(client: TestClient):
    """Verify that Hunar webhook payload with call_id is processed and idempotent."""
    call_id = f"hunar-call-{uuid.uuid4().hex[:8]}"

    # Insert a mock CallSession in in_progress state
    with Session(engine) as session:
        call = CallSession(
            candidate_id=uuid.uuid4(),
            status="in_progress",
            external_call_id=call_id,
        )
        session.add(call)
        session.commit()
        session.refresh(call)

    # Official Hunar call_summary webhook payload
    payload = {
        "event_type": "call_summary",
        "call_id": call_id,
        "status": "COMPLETED",
        "duration_seconds": 195.5,
        "recording_url": "https://recordings.hunar.ai/test-call.mp3",
        "result": {
            "interested": True,
            "qualified": True,
            "summary": "Candidate passed the initial screening.",
        },
    }

    with patch("app.webhooks.router.extract_transcript") as mock_task:
        mock_task.delay = lambda *a, **k: None

        # First call should succeed
        resp1 = client.post("/webhooks/voice-call", json=payload)
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "success"

        # Second call should be ignored due to idempotency
        resp2 = client.post("/webhooks/voice-call", json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ignored"
        assert resp2.json()["detail"] == "already processed"


def test_hunar_webhook_signature_validation(client: TestClient):
    """Verify that Hunar webhook signature validates using HUNAR_API_KEY (no webhook secret needed)."""
    call_id = f"hunar-call-{uuid.uuid4().hex[:8]}"
    test_api_key = "hunar_test_api_key_12345"

    with Session(engine) as session:
        call = CallSession(
            candidate_id=uuid.uuid4(),
            status="in_progress",
            external_call_id=call_id,
        )
        session.add(call)
        session.commit()

    payload = {
        "event_type": "call_summary",
        "call_id": call_id,
        "status": "COMPLETED",
        "duration_seconds": 120.0,
    }
    raw_body = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))

    # Compute valid signature using the API key
    valid_sig = compute_hunar_signature(
        api_key=test_api_key,
        request_body=raw_body,
        timestamp=timestamp,
    )

    with patch.object(settings, "HUNAR_API_KEY", test_api_key):
        with patch("app.webhooks.router.extract_transcript") as mock_task:
            mock_task.delay = lambda *a, **k: None

            # Request with valid signature should succeed
            resp = client.post(
                "/webhooks/voice-call",
                content=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hunar-Signature": valid_sig,
                    "X-Hunar-Timestamp": timestamp,
                },
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"

            # Request with tampered signature should be rejected with 401
            bad_resp = client.post(
                "/webhooks/voice-call",
                content=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hunar-Signature": "invalid_base64_sig==",
                    "X-Hunar-Timestamp": timestamp,
                },
            )
            assert bad_resp.status_code == 401


def test_webhook_unknown_call_id(client: TestClient):
    """Webhook should ignore payloads with an unknown call_id."""
    payload = {
        "event_type": "call_summary",
        "call_id": "nonexistent-call-uuid",
        "status": "COMPLETED",
    }
    resp = client.post("/webhooks/voice-call", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert resp.json()["detail"] == "session not found"
