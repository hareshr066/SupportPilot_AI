import hmac
import hashlib
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings
from app.api.main import create_app
from app.database.models import Base, Repository, WebhookEvent, Issue
from app.database.session import get_db_session

# Setup in-memory SQLite engine for webhook testing
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


def override_get_db():
    db = TestingSessionLocal(bind=engine)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_db_session] = override_get_db
    with TestClient(app) as c:
        yield c


def compute_signature(payload_bytes: bytes, secret: str = "dev_webhook_secret_key_12345") -> str:
    sig = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def test_webhook_missing_headers(client):
    response = client.post("/api/v1/webhooks/github", json={"test": "data"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_webhook_invalid_signature(client):
    payload = json.dumps({"test": "data"}).encode("utf-8")
    headers = {
        "X-GitHub-Delivery": "del_001",
        "X-GitHub-Event": "issues",
        "X-Hub-Signature-256": "sha256=invalid_signature_hex"
    }
    response = client.post("/api/v1/webhooks/github", content=payload, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_webhook_unregistered_repository(client):
    payload_dict = {
        "action": "opened",
        "repository": {"full_name": "owner/unregistered"},
        "issue": {
            "id": 100,
            "number": 1,
            "title": "Test Issue",
            "body": "Body text",
            "state": "open",
            "html_url": "https://github.com/owner/unregistered/issues/1"
        }
    }
    payload_bytes = json.dumps(payload_dict).encode("utf-8")
    sig = compute_signature(payload_bytes)

    headers = {
        "X-GitHub-Delivery": "del_002",
        "X-GitHub-Event": "issues",
        "X-Hub-Signature-256": sig
    }

    response = client.post("/api/v1/webhooks/github", content=payload_bytes, headers=headers)
    assert response.status_code == 202
    res_data = response.json()
    assert res_data["status"] == "FAILED"
    assert res_data["delivery_id"] == "del_002"


def test_webhook_issues_opened_success(client):
    # Seed repository in test DB
    with TestingSessionLocal(bind=engine) as db:
        repo = Repository(
            owner="microsoft",
            name="vscode",
            full_name="microsoft/vscode",
            html_url="https://github.com/microsoft/vscode",
            enabled=True,
            webhook_enabled=True,
            auto_analysis_enabled=True
        )
        db.add(repo)
        db.commit()

    payload_dict = {
        "action": "opened",
        "repository": {"full_name": "microsoft/vscode"},
        "issue": {
            "id": 8888,
            "number": 101,
            "title": "Terminal pty exit code 1",
            "body": "Process exits immediately.",
            "state": "open",
            "html_url": "https://github.com/microsoft/vscode/issues/101"
        }
    }
    payload_bytes = json.dumps(payload_dict).encode("utf-8")
    sig = compute_signature(payload_bytes)

    headers = {
        "X-GitHub-Delivery": "del_003",
        "X-GitHub-Event": "issues",
        "X-Hub-Signature-256": sig
    }

    mock_pipeline_res = MagicMock()
    mock_pipeline_res.pipeline_run_id = "run_mock_123"

    with patch("app.services.webhook_service.run_support_pipeline", return_value=mock_pipeline_res):
        response = client.post("/api/v1/webhooks/github", content=payload_bytes, headers=headers)
        assert response.status_code == 202
        res_data = response.json()
        assert res_data["delivery_id"] == "del_003"
        assert res_data["status"] == "PROCESSED"
        assert res_data["pipeline_run_id"] == "run_mock_123"

    # Verify Issue was persisted in DB
    with TestingSessionLocal(bind=engine) as db:
        issue = db.query(Issue).filter_by(issue_number=101).first()
        assert issue is not None
        assert issue.title == "Terminal pty exit code 1"


def test_webhook_idempotency_duplicate_delivery(client):
    with TestingSessionLocal(bind=engine) as db:
        repo = Repository(
            owner="microsoft",
            name="vscode",
            full_name="microsoft/vscode"
        )
        db.add(repo)
        db.commit()

    payload_dict = {
        "action": "opened",
        "repository": {"full_name": "microsoft/vscode"},
        "issue": {
            "id": 9999,
            "number": 102,
            "title": "Duplicate delivery issue",
            "body": "Testing idempotency",
            "state": "open",
            "html_url": "https://github.com/microsoft/vscode/issues/102"
        }
    }
    payload_bytes = json.dumps(payload_dict).encode("utf-8")
    sig = compute_signature(payload_bytes)

    headers = {
        "X-GitHub-Delivery": "del_duplicate_001",
        "X-GitHub-Event": "issues",
        "X-Hub-Signature-256": sig
    }

    mock_pipeline_res = MagicMock()
    mock_pipeline_res.pipeline_run_id = "run_mock_456"

    with patch("app.services.webhook_service.run_support_pipeline", return_value=mock_pipeline_res):
        # First delivery
        res1 = client.post("/api/v1/webhooks/github", content=payload_bytes, headers=headers)
        assert res1.status_code == 202

        # Second delivery with exact same delivery_id
        res2 = client.post("/api/v1/webhooks/github", content=payload_bytes, headers=headers)
        assert res2.status_code == 202
        assert res2.json()["delivery_id"] == "del_duplicate_001"

    # Verify only 1 webhook_event record was created
    with TestingSessionLocal(bind=engine) as db:
        count = db.query(WebhookEvent).filter_by(delivery_id="del_duplicate_001").count()
        assert count == 1
