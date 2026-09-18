import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings
from app.api.main import create_app
from app.database.models import Base, Issue, Repository
from app.database.session import get_db_session

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


def override_get_db():
    db = TestingSessionLocal()
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
    test_app = create_app()
    test_app.dependency_overrides[get_db_session] = override_get_db
    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


def test_create_external_ticket_success(client):
    """Verify POST /v1/tickets creates persistent ticket and returns SP-XXXX ID."""
    payload = {
        "title": "Study progress resets after refresh",
        "description": "After reviewing flashcards, today's study progress disappears after refreshing the application.",
        "application": "StudySync",
        "environment": "production",
        "feature": "study-progress"
    }

    res = client.post("/v1/tickets", json=payload)
    assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"

    data = res.json()
    assert "ticket_id" in data
    assert data["ticket_id"].startswith("SP-")
    assert data["status"] == "RECEIVED"
    assert data["application"] == "StudySync"
    assert data["title"] == payload["title"]

    # Verify database persistence
    db_id = int(data["ticket_id"].replace("SP-", ""))
    session = TestingSessionLocal()
    try:
        issue = session.scalar(select(Issue).where(Issue.id == db_id))
        assert issue is not None
        assert issue.title == payload["title"]
        assert issue.body == payload["description"]
        assert issue.state == "RECEIVED"
        assert issue.repository.owner == "StudySync"
    finally:
        session.close()


def test_create_external_ticket_validation_failure(client):
    """Verify POST /v1/tickets validates empty or whitespace titles."""
    payload = {
        "title": "   ",
        "description": "Some description",
        "application": "StudySync"
    }
    res = client.post("/v1/tickets", json=payload)
    assert res.status_code == 400


def test_get_external_tickets_list_and_detail(client):
    """Verify GET /v1/tickets and GET /v1/tickets/{ticket_id}."""
    create_res = client.post("/v1/tickets", json={
        "title": "Sync button frozen",
        "description": "Sync button remains disabled indefinitely.",
        "application": "StudySync"
    })
    assert create_res.status_code == 201
    ticket_id = create_res.json()["ticket_id"]

    # 1. GET /v1/tickets
    list_res = client.get("/v1/tickets")
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) >= 1
    assert any(it["ticket_id"] == ticket_id for it in items)

    # 2. GET /v1/tickets/{ticket_id}
    detail_res = client.get(f"/v1/tickets/{ticket_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["ticket_id"] == ticket_id
    assert detail["title"] == "Sync button frozen"
    assert detail["application"] == "StudySync"


def test_analyze_external_ticket_by_id(client):
    """Verify POST /v1/tickets/{ticket_id}/analyze triggers LangGraph investigation."""
    create_res = client.post("/v1/tickets", json={
        "title": "Study progress resets after refresh",
        "description": "After reviewing flashcards, today's study progress disappears.",
        "application": "StudySync"
    })
    assert create_res.status_code == 201
    ticket_id = create_res.json()["ticket_id"]

    analyze_res = client.post(f"/v1/tickets/{ticket_id}/analyze")
    assert analyze_res.status_code == 200

    data = analyze_res.json()
    assert "pipeline_run_id" in data
    assert "status" in data
    assert "final_decision" in data


def test_api_key_authentication_hardening(client):
    """Verify SUPPORTPILOT_API_KEY authorization enforcement."""
    original_key = settings.supportpilot_api_key
    settings.supportpilot_api_key = "secret_studysync_key_999"
    try:
        payload = {
            "title": "Unauthorized attempt ticket",
            "description": "Testing security boundary.",
            "application": "StudySync"
        }

        # 1. Unauthorized request without header -> 401
        unauth_res = client.post("/v1/tickets", json=payload)
        assert unauth_res.status_code == 401

        # 2. Invalid API key -> 401
        invalid_res = client.post("/v1/tickets", json=payload, headers={"X-API-Key": "wrong_key"})
        assert invalid_res.status_code == 401

        # 3. Valid API key via X-API-Key -> 201
        valid_res_1 = client.post("/v1/tickets", json=payload, headers={"X-API-Key": "secret_studysync_key_999"})
        assert valid_res_1.status_code == 201

        # 4. Valid API key via Bearer token -> 201
        valid_res_2 = client.post("/v1/tickets", json=payload, headers={"Authorization": "Bearer secret_studysync_key_999"})
        assert valid_res_2.status_code == 201
    finally:
        settings.supportpilot_api_key = original_key
