import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.api.main import app
from app.database.session import get_db_session
from app.database.models import PipelineRun, PipelineStageRun
from app.schemas.pipeline_schemas import PipelineResult

client = TestClient(app)


def test_health_endpoint():
    """1. Test GET /health returns 200 and expected json."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["service"] == "supportpilot"


def test_ready_endpoint_ready():
    """2. Test GET /ready returns 200 when database connection succeeds."""
    mock_session = MagicMock()
    mock_session.execute.return_value.scalar.return_value = 1

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        res = client.get("/ready")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"] == "ok"
    finally:
        app.dependency_overrides.clear()


def test_empty_title_validation_failure():
    """4. Test empty title returns 400 with structured INVALID_INPUT error."""
    payload = {
        "repository_id": 1,
        "title": "   ",
        "body": "Some body"
    }
    res = client.post("/api/v1/tickets/analyze", json=payload)
    assert res.status_code == 400
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_INPUT"
    assert "request_id" in data["error"]


def test_missing_repository_validation_failure():
    """5. Test missing repository_id returns 400."""
    payload = {
        "title": "Valid Title"
    }
    res = client.post("/api/v1/tickets/analyze", json=payload)
    assert res.status_code == 400
    data = res.json()
    assert data["error"]["code"] == "INVALID_INPUT"


@patch("app.api.routes.tickets.run_support_pipeline")
def test_analyze_ticket_success(mock_run_pipeline):
    """3, 7. Test POST /api/v1/tickets/analyze success flow."""
    mock_run_pipeline.return_value = PipelineResult(
        pipeline_run_id="pipeline_api_test_123",
        ticket_id=1,
        status="SUCCEEDED",
        final_decision="AUTO_RESOLVE_RECOMMENDATION",
        recommended_team="terminal-maintainers",
        calibrated_confidence=0.92,
        routing_probability=0.90,
        human_review_required=False,
        total_latency_ms=150.0,
        stage_latencies={"classify_severity": 10.0},
        stage_statuses={"classify_severity": "SUCCEEDED"},
        audit_reference="artifacts/pipeline/run_1.json"
    )

    payload = {
        "repository_id": 1,
        "title": "Terminal pty crash",
        "body": "Exit code 1 on launch"
    }
    res = client.post("/api/v1/tickets/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["pipeline_run_id"] == "pipeline_api_test_123"
    assert data["final_decision"] == "AUTO_RESOLVE_RECOMMENDATION"
    assert data["human_review_required"] is False


@patch("app.api.routes.tickets.replay_pipeline_run")
@patch("app.api.routes.tickets.run_support_pipeline")
def test_idempotency_header_key(mock_run_pipeline, mock_replay_pipeline):
    """18. Test optional Idempotency-Key header reuses previous run result."""
    mock_run_pipeline.return_value = PipelineResult(
        pipeline_run_id="pipeline_idem_1",
        status="SUCCEEDED",
        final_decision="AUTO_RESOLVE_RECOMMENDATION",
        audit_reference="artifacts/pipeline/run_idem.json"
    )
    mock_replay_pipeline.return_value = PipelineResult(
        pipeline_run_id="pipeline_idem_1",
        status="SUCCEEDED",
        final_decision="AUTO_RESOLVE_RECOMMENDATION",
        audit_reference="artifacts/pipeline/run_idem.json"
    )

    headers = {"Idempotency-Key": "idem_key_unique_999"}
    payload = {"repository_id": 1, "title": "First request"}

    # First Request
    res1 = client.post("/api/v1/tickets/analyze", json=payload, headers=headers)
    assert res1.status_code == 200
    assert mock_run_pipeline.call_count == 1

    # Second Request with same Idempotency-Key
    res2 = client.post("/api/v1/tickets/analyze", json=payload, headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["pipeline_run_id"] == "pipeline_idem_1"


def test_get_run_status_not_found():
    """10. Test GET /api/v1/runs/{id} returns 404 if run not found."""
    mock_session = MagicMock()
    mock_session.scalar.return_value = None

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        res = client.get("/api/v1/runs/pipeline_nonexistent_999")
        assert res.status_code == 404
        data = res.json()
        assert data["error"]["code"] == "NOT_FOUND"
    finally:
        app.dependency_overrides.clear()


def test_get_run_status_success():
    """11. Test GET /api/v1/runs/{id} returns status summary."""
    mock_session = MagicMock()
    mock_run = PipelineRun(
        pipeline_run_id="pipeline_rec_1",
        ticket_id=1,
        status="SUCCEEDED",
        final_decision="AUTO_RESOLVE_RECOMMENDATION",
        recommended_team="terminal-maintainers",
        calibrated_confidence=0.91,
        routing_probability=0.88,
        total_latency_ms=120.0,
        created_at=datetime.now(timezone.utc)
    )
    mock_session.scalar.return_value = mock_run

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        res = client.get("/api/v1/runs/pipeline_rec_1")
        assert res.status_code == 200
        data = res.json()
        assert data["pipeline_run_id"] == "pipeline_rec_1"
        assert data["final_decision"] == "AUTO_RESOLVE_RECOMMENDATION"
    finally:
        app.dependency_overrides.clear()


@patch("app.api.routes.runs.replay_pipeline_run")
def test_get_run_result_success(mock_replay):
    """11. Test GET /api/v1/runs/{id}/result returns full PipelineResult."""
    mock_replay.return_value = PipelineResult(
        pipeline_run_id="pipeline_rec_1",
        status="SUCCEEDED",
        final_decision="AUTO_RESOLVE_RECOMMENDATION",
        audit_reference="artifacts/pipeline/run_rec.json"
    )

    res = client.get("/api/v1/runs/pipeline_rec_1/result")
    assert res.status_code == 200
    data = res.json()
    assert data["pipeline_run_id"] == "pipeline_rec_1"


def test_get_run_stages_success():
    """12. Test GET /api/v1/runs/{id}/stages returns stage latency list."""
    mock_session = MagicMock()
    mock_run = PipelineRun(pipeline_run_id="pipeline_rec_1")
    mock_stage = PipelineStageRun(
        pipeline_run_id="pipeline_rec_1",
        stage_name="classify_severity",
        status="SUCCEEDED",
        latency_ms=42.5
    )
    mock_session.scalar.return_value = mock_run
    mock_session.scalars.return_value.all.return_value = [mock_stage]

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        res = client.get("/api/v1/runs/pipeline_rec_1/stages")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["stage"] == "classify_severity"
        assert data[0]["latency_ms"] == 42.5
    finally:
        app.dependency_overrides.clear()


@patch("app.api.routes.runs.replay_pipeline_run")
def test_get_run_escalation_endpoint(mock_replay):
    """14. Test GET /api/v1/runs/{id}/escalation returns escalation package."""
    mock_replay.return_value = PipelineResult(
        pipeline_run_id="pipeline_esc_1",
        status="ESCALATED",
        final_decision="HUMAN_ESCALATION",
        human_review_required=True,
        escalation_package={"reason_codes": ["CONFIDENCE_BELOW_THRESHOLD"], "suggested_team": "GENERAL_SUPPORT_QUEUE"},
        audit_reference="artifacts/pipeline/run_esc.json"
    )

    res = client.get("/api/v1/runs/pipeline_esc_1/escalation")
    assert res.status_code == 200
    data = res.json()
    assert data["escalated"] is True
    assert "CONFIDENCE_BELOW_THRESHOLD" in data["reason_codes"]


@patch("app.api.routes.runs.replay_pipeline_run")
def test_get_run_evidence_endpoint(mock_replay):
    """13. Test GET /api/v1/runs/{id}/evidence returns evidence summary."""
    mock_replay.return_value = PipelineResult(
        pipeline_run_id="pipeline_ev_1",
        status="SUCCEEDED",
        final_decision="AUTO_RESOLVE_RECOMMENDATION",
        retrieval={
            "evidence_completeness": 0.85,
            "retrieved_cases": [
                {"issue_id": 101, "issue_number": 5, "title": "Previous fix", "dense_similarity": 0.82}
            ]
        },
        audit_reference="artifacts/pipeline/run_ev.json"
    )

    res = client.get("/api/v1/runs/pipeline_ev_1/evidence")
    assert res.status_code == 200
    data = res.json()
    assert data["evidence_completeness"] == 0.85
    assert len(data["retrieved_cases"]) == 1
    assert data["retrieved_cases"][0]["issue_id"] == 101


def test_cors_headers():
    """17. Test CORS preflight and origin validation."""
    res = client.options(
        "/api/v1/tickets/analyze",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"}
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_request_id_and_security_headers():
    """15, 29. Test request ID injection and security headers."""
    res = client.get("/health")
    assert res.status_code == 200
    assert "X-Request-ID" in res.headers
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
