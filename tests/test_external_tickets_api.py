import pytest
from unittest.mock import MagicMock
from contextlib import contextmanager
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings
from app.api.main import create_app
from app.database.models import Base, Issue, Repository, PipelineRun
from app.database.session import get_db_session
from app.schemas.pipeline_schemas import PipelineResult
from app.api.routes.tickets import (
    _TICKET_IDEMPOTENCY_CACHE,
    _IDEMPOTENCY_CACHE,
    _IN_FLIGHT_ANALYSES,
    _IN_FLIGHT_LOCK,
    trigger_automatic_ticket_analysis,
)

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


@contextmanager
def override_get_db_ctx():
    db = TestingSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.database.session.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("app.database.session.get_db", override_get_db_ctx)
    monkeypatch.setattr("app.services.pipeline_orchestrator.get_db", override_get_db_ctx)
    monkeypatch.setattr("app.api.routes.tickets.get_db", override_get_db_ctx)
    with _IN_FLIGHT_LOCK:
        _IN_FLIGHT_ANALYSES.clear()
    _TICKET_IDEMPOTENCY_CACHE.clear()
    _IDEMPOTENCY_CACHE.clear()
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


def test_automatic_analysis_triggered_and_persisted(client, monkeypatch):
    """Verify ticket creation automatically triggers AI analysis and records PipelineRun in DB."""
    recorded_inputs = []

    def mock_pipeline(ticket_inp):
        recorded_inputs.append(ticket_inp)
        with override_get_db_ctx() as session:
            run_rec = PipelineRun(
                pipeline_run_id=f"pipeline_auto_{ticket_inp.ticket_id}",
                ticket_id=ticket_inp.ticket_id,
                status="SUCCEEDED",
                final_decision="AUTO_RESOLVE_RECOMMENDATION",
                recommended_team="GENERAL_SUPPORT_QUEUE",
                calibrated_confidence=0.94,
                routing_probability=0.91,
                total_latency_ms=120.0,
                created_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc)
            )
            session.add(run_rec)
            session.commit()
        return PipelineResult(
            pipeline_run_id=f"pipeline_auto_{ticket_inp.ticket_id}",
            ticket_id=ticket_inp.ticket_id,
            status="SUCCEEDED",
            final_decision="AUTO_RESOLVE_RECOMMENDATION",
            recommended_team="GENERAL_SUPPORT_QUEUE",
            calibrated_confidence=0.94,
            routing_probability=0.91,
            human_review_required=False,
            total_latency_ms=120.0,
            stage_latencies={},
            stage_statuses={},
            audit_reference="artifacts/pipeline/summary.json"
        )

    monkeypatch.setattr("app.api.routes.tickets.run_support_pipeline", mock_pipeline)

    payload = {
        "title": "Cannot export flashcards to PDF",
        "description": "Export button shows spinner indefinitely when selecting PDF format.",
        "application": "StudySync",
        "environment": "production"
    }

    res = client.post("/v1/tickets", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "RECEIVED"
    ticket_id = int(data["ticket_id"].replace("SP-", ""))

    # Verify run_support_pipeline was automatically triggered with correct ticket and repository
    assert len(recorded_inputs) == 1
    assert recorded_inputs[0].ticket_id == ticket_id
    assert recorded_inputs[0].title == payload["title"]
    assert recorded_inputs[0].body == payload["description"]

    # Verify database persistence: Issue is intact and PipelineRun is recorded
    session = TestingSessionLocal()
    try:
        issue = session.scalar(select(Issue).where(Issue.id == ticket_id))
        assert issue is not None
        assert issue.state == "RECEIVED"
        assert issue.title == payload["title"]

        run = session.scalar(select(PipelineRun).where(PipelineRun.ticket_id == ticket_id))
        assert run is not None
        assert run.status == "SUCCEEDED"
        assert run.final_decision == "AUTO_RESOLVE_RECOMMENDATION"
        assert run.pipeline_run_id == f"pipeline_auto_{ticket_id}"
    finally:
        session.close()


def test_automatic_analysis_failure_preserves_ticket_and_logs(client, monkeypatch):
    """Verify that if pipeline analysis fails, original ticket is preserved and FAILED status is recorded."""
    def failing_pipeline(ticket_inp):
        raise RuntimeError("LLM cluster network connection refused")

    monkeypatch.setattr("app.api.routes.tickets.run_support_pipeline", failing_pipeline)

    payload = {
        "title": "Study timer pauses on tab switch",
        "description": "Focus mode timer does not count down when tab is in background.",
        "application": "StudySync"
    }

    res = client.post("/v1/tickets", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "RECEIVED"
    ticket_id = int(data["ticket_id"].replace("SP-", ""))

    # Verify original ticket in database was preserved intact
    session = TestingSessionLocal()
    try:
        issue = session.scalar(select(Issue).where(Issue.id == ticket_id))
        assert issue is not None
        assert issue.title == payload["title"]
        assert issue.body == payload["description"]
        assert issue.state == "RECEIVED"

        # Verify a FAILED PipelineRun record was created with error details
        failed_run = session.scalar(select(PipelineRun).where(PipelineRun.ticket_id == ticket_id))
        assert failed_run is not None
        assert failed_run.status == "FAILED"
        assert failed_run.error_code == "AUTOMATIC_ANALYSIS_ERROR"
        assert "LLM cluster network connection refused" in (failed_run.error_message or "")
    finally:
        session.close()


def test_duplicate_trigger_prevention_via_idempotency_key(client, monkeypatch):
    """Verify repeated POST /v1/tickets with same Idempotency-Key returns existing ticket and prevents duplicate runs."""
    call_count = 0

    def mock_pipeline(ticket_inp):
        nonlocal call_count
        call_count += 1
        with override_get_db_ctx() as session:
            run_rec = PipelineRun(
                pipeline_run_id=f"pipeline_idemp_{ticket_inp.ticket_id}",
                ticket_id=ticket_inp.ticket_id,
                status="SUCCEEDED",
                final_decision="AUTO_RESOLVE_RECOMMENDATION",
                created_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc)
            )
            session.add(run_rec)
            session.commit()
        return PipelineResult(
            pipeline_run_id=f"pipeline_idemp_{ticket_inp.ticket_id}",
            ticket_id=ticket_inp.ticket_id,
            status="SUCCEEDED",
            final_decision="AUTO_RESOLVE_RECOMMENDATION",
            audit_reference="audit.json"
        )

    monkeypatch.setattr("app.api.routes.tickets.run_support_pipeline", mock_pipeline)

    payload = {
        "title": "Dark mode setting resets on logout",
        "description": "Theme preferences are not persisted across sessions.",
        "application": "StudySync"
    }
    headers = {"Idempotency-Key": "req_key_999888"}

    res1 = client.post("/v1/tickets", json=payload, headers=headers)
    assert res1.status_code == 201
    ticket_id_1 = res1.json()["ticket_id"]

    # Send exact same request again with identical Idempotency-Key
    res2 = client.post("/v1/tickets", json=payload, headers=headers)
    assert res2.status_code == 201
    ticket_id_2 = res2.json()["ticket_id"]

    # Both requests return identical ticket ID
    assert ticket_id_1 == ticket_id_2

    # Analysis was only executed once
    assert call_count == 1

    # Verify only 1 ticket was created in DB
    session = TestingSessionLocal()
    try:
        issue_count = session.scalar(select(func.count(Issue.id)))
        assert issue_count == 1
    finally:
        session.close()


def test_duplicate_trigger_prevention_via_external_ticket_id(client, monkeypatch):
    """Verify repeated requests with same external_ticket_id in payload prevent duplicate analysis."""
    call_count = 0

    def mock_pipeline(ticket_inp):
        nonlocal call_count
        call_count += 1
        return PipelineResult(
            pipeline_run_id=f"pipeline_ext_{ticket_inp.ticket_id}",
            ticket_id=ticket_inp.ticket_id,
            status="SUCCEEDED",
            final_decision="AUTO_RESOLVE_RECOMMENDATION",
            audit_reference="audit.json"
        )

    monkeypatch.setattr("app.api.routes.tickets.run_support_pipeline", mock_pipeline)

    payload = {
        "title": "Flashcard audio playback delayed",
        "description": "Audio clips take 3 seconds to start playing.",
        "application": "StudySync",
        "external_ticket_id": "STUDYSYNC-EXT-442"
    }

    res1 = client.post("/v1/tickets", json=payload)
    assert res1.status_code == 201
    ticket_id_1 = res1.json()["ticket_id"]

    res2 = client.post("/v1/tickets", json=payload)
    assert res2.status_code == 201
    ticket_id_2 = res2.json()["ticket_id"]

    assert ticket_id_1 == ticket_id_2
    assert call_count == 1


def test_duplicate_trigger_prevention_existing_run_and_in_flight(client, monkeypatch):
    """Verify trigger_automatic_ticket_analysis skips tickets that already have a run or are in-flight."""
    call_count = 0

    def mock_pipeline(ticket_inp):
        nonlocal call_count
        call_count += 1
        return PipelineResult(
            pipeline_run_id=f"pipeline_{ticket_inp.ticket_id}",
            ticket_id=ticket_inp.ticket_id,
            status="SUCCEEDED",
            final_decision="AUTO_RESOLVE_RECOMMENDATION",
            audit_reference="audit.json"
        )

    monkeypatch.setattr("app.api.routes.tickets.run_support_pipeline", mock_pipeline)

    session = TestingSessionLocal()
    repo = Repository(owner="StudySync", name="main", full_name="StudySync/main", auto_analysis_enabled=True)
    session.add(repo)
    session.commit()
    issue = Issue(
        github_issue_id=12345,
        repository_id=repo.id,
        issue_number=1,
        title="Test issue",
        body="Body",
        state="RECEIVED",
        created_at=datetime.now(timezone.utc),
        html_url="https://test"
    )
    session.add(issue)
    session.commit()

    # 1. Ticket in-flight check
    with _IN_FLIGHT_LOCK:
        _IN_FLIGHT_ANALYSES.add(issue.id)

    trigger_automatic_ticket_analysis(
        ticket_id=issue.id,
        repository_id=repo.id,
        title=issue.title,
        body=issue.body,
        issue_number=issue.issue_number
    )
    assert call_count == 0  # Skipped because in-flight

    with _IN_FLIGHT_LOCK:
        _IN_FLIGHT_ANALYSES.discard(issue.id)

    # 2. Ticket already has completed run in DB
    completed_run = PipelineRun(
        pipeline_run_id="pipeline_existing_completed",
        ticket_id=issue.id,
        status="SUCCEEDED",
        final_decision="AUTO_RESOLVE_RECOMMENDATION",
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc)
    )
    session.add(completed_run)
    session.commit()
    session.close()

    trigger_automatic_ticket_analysis(
        ticket_id=issue.id,
        repository_id=repo.id,
        title=issue.title,
        body=issue.body,
        issue_number=issue.issue_number
    )
    assert call_count == 0  # Skipped because already in DB


def test_dashboard_metrics_reflect_automatic_analysis(client, monkeypatch):
    """Verify that automatically analyzed tickets immediately appear in dashboard metrics and recent runs."""
    def mock_pipeline(ticket_inp):
        with override_get_db_ctx() as session:
            run_rec = PipelineRun(
                pipeline_run_id=f"pipeline_dash_{ticket_inp.ticket_id}",
                ticket_id=ticket_inp.ticket_id,
                status="SUCCEEDED",
                final_decision="AUTO_RESOLVE_RECOMMENDATION",
                recommended_team="GENERAL_SUPPORT_QUEUE",
                total_latency_ms=105.0,
                created_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc)
            )
            session.add(run_rec)
            session.commit()
        return PipelineResult(
            pipeline_run_id=f"pipeline_dash_{ticket_inp.ticket_id}",
            ticket_id=ticket_inp.ticket_id,
            status="SUCCEEDED",
            final_decision="AUTO_RESOLVE_RECOMMENDATION",
            audit_reference="audit.json"
        )

    monkeypatch.setattr("app.api.routes.tickets.run_support_pipeline", mock_pipeline)

    # Create ticket
    res = client.post("/v1/tickets", json={
        "title": "StudySync session disconnects during quiz",
        "description": "Network timeout during multiple choice quizzes.",
        "application": "StudySync"
    })
    assert res.status_code == 201

    # Verify dashboard summary
    dash_res = client.get("/api/v1/dashboard/summary")
    assert dash_res.status_code == 200
    summary = dash_res.json()
    assert summary["total_tickets"] >= 1
    assert summary["analyzed_today"] >= 1
    assert summary["auto_resolution_recommendations"] >= 1

    # Verify dashboard recent runs
    runs_res = client.get("/api/v1/dashboard/recent-runs")
    assert runs_res.status_code == 200
    runs = runs_res.json()
    assert len(runs) >= 1
    assert any(r["title"] == "StudySync session disconnects during quiz" for r in runs)


def test_e2e_automatic_analysis_with_studysync_retrieval_and_dashboard(client, monkeypatch):
    """End-to-end verification of automatic analysis:
    - Creates ticket via POST /v1/tickets
    - Automatic analysis runs the pipeline
    - PipelineRun reaches terminal status (SUCCEEDED or ESCALATED)
    - Dashboard summary and recent-runs reflect the result
    """
    session = TestingSessionLocal()
    repo_vscode = Repository(owner="microsoft", name="vscode", full_name="microsoft/vscode", auto_analysis_enabled=True)
    repo_studysync = Repository(owner="StudySync", name="main", full_name="StudySync/main", auto_analysis_enabled=True)
    session.add_all([repo_vscode, repo_studysync])
    session.commit()

    now = datetime.now(timezone.utc)
    iss_vscode = Issue(
        github_issue_id=901,
        repository_id=repo_vscode.id,
        issue_number=1,
        title="Terminal crash on exit code 1",
        body="VS Code terminal crashes on startup",
        state="closed",
        created_at=now,
        html_url="https://github.com/microsoft/vscode/issues/1"
    )
    iss_studysync = Issue(
        github_issue_id=902,
        repository_id=repo_studysync.id,
        issue_number=10,
        title="Study progress resets after page refresh due to missing localStorage sync on unload",
        body="StudySync study session loses progress vectors on browser refresh",
        state="closed",
        created_at=now,
        html_url="https://github.com/StudySync/main/issues/10"
    )
    session.add_all([iss_vscode, iss_studysync])
    session.commit()
    session.close()

    # Deterministic mocks for external model inference
    monkeypatch.setattr(
        "app.services.pipeline_orchestrator.SeverityClassifierService.predict_severity",
        lambda self, title, body: {"predicted_severity": "medium", "confidence": 0.85, "probabilities": {"medium": 0.85}}
    )
    monkeypatch.setattr(
        "app.services.pipeline_orchestrator.DuplicateDetector.detect_duplicate",
        lambda self, title, body, repository_id=None: {"is_duplicate": False, "confidence": 0.05, "candidates": []}
    )
    monkeypatch.setattr(
        "app.services.pipeline_orchestrator.GroundedResolutionService.generate_resolution",
        lambda self, request, session: (
            MagicMock(model_dump=lambda: {
                "summary": "Fix localStorage sync in beforeunload event handler.",
                "claims": ["Adds beforeunload listener to flush progress vectors."],
                "citations": ["https://github.com/StudySync/main/issues/10"]
            }),
            MagicMock(),
            "res_run_e2e_1"
        )
    )
    monkeypatch.setattr(
        "app.services.pipeline_orchestrator.ClaimVerificationService.verify_resolution",
        lambda self, res_summary, claims, retrieved_cases, request, session, resolution_run_id=None: {
            "verification_run_id": "ver_run_e2e_1",
            "overall_faithfulness_status": "FULLY_SUPPORTED",
            "has_critical_failure": False,
            "contradicted_count": 0,
            "unsupported_count": 0,
            "supported_count": 1,
            "total_claims": 1,
            "strict_faithfulness": 1.0
        }
    )
    monkeypatch.setattr(
        "app.services.pipeline_orchestrator.ConfidenceCalibrationService.compute_confidence_and_decision",
        lambda self, **kwargs: MagicMock(
            model_dump=lambda: {
                "calibrated_confidence": 0.95,
                "decision": "AUTO_RESOLVE",
                "threshold": 0.80,
                "reason_codes": ["ALL_CLAIMS_SUPPORTED"],
                "model_version": "test",
                "feature_version": "test",
                "threshold_version": "test"
            }
        )
    )
    monkeypatch.setattr(
        "app.services.pipeline_orchestrator.RoutingEngineService.predict_route",
        lambda self, **kwargs: MagicMock(
            model_dump=lambda: {
                "predicted_component": "ProgressSync",
                "routing_probability": 0.92,
                "target_team": "CORE_SUPPORT",
                "routing_run_id": "rout_1"
            }
        )
    )
    monkeypatch.setattr(
        "app.services.pipeline_orchestrator.DeterministicDecisionEngine.make_final_decision",
        lambda self, **kwargs: MagicMock(
            model_dump=lambda: {
                "final_decision": "AUTO_RESOLVE",
                "recommended_team": "CORE_SUPPORT",
                "confidence_score": 0.95,
                "auto_resolved": True,
                "reason_codes": ["ALL_CLAIMS_SUPPORTED"]
            }
        )
    )

    payload = {
        "title": "Study progress resets on refresh",
        "description": "Progress vectors missing after reload",
        "application": "StudySync",
        "environment": "production"
    }
    res = client.post("/v1/tickets", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["ticket_id"].startswith("SP-")
    assert data["status"] == "RECEIVED"
    assert data["application"] == "StudySync"
    db_id = int(data["ticket_id"].replace("SP-", ""))

    s = TestingSessionLocal()
    try:
        run = s.scalar(select(PipelineRun).where(PipelineRun.ticket_id == db_id))
        assert run is not None
        assert run.status in ["SUCCEEDED", "ESCALATED"]
        assert run.final_decision in ["AUTO_RESOLVE_RECOMMENDATION", "AUTO_RESOLVE", "HUMAN_ESCALATION"]
        assert run.total_latency_ms >= 0.0

        summary_res = client.get("/api/v1/dashboard/summary")
        assert summary_res.status_code == 200
        summary_data = summary_res.json()
        assert summary_data["total_tickets"] >= 1
        assert summary_data["analyzed_today"] >= 1

        recent_res = client.get("/api/v1/dashboard/recent-runs")
        assert recent_res.status_code == 200
        recent_items = recent_res.json()
        assert any(item["ticket_id"] == db_id for item in recent_items)
    finally:
        s.close()
