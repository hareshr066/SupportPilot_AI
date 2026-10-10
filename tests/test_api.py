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


def test_dashboard_metrics_and_recent_runs_regression():
    """Regression test for dashboard metrics semantics and recent runs."""
    from datetime import timedelta
    from app.database.models import Issue, PipelineRun, PipelineStageRun, SeverityPrediction

    now = datetime.now(timezone.utc)
    mock_session = MagicMock()

    # 3 issues (2 open, 1 closed)
    issue_open1 = Issue(id=1, issue_number=1, repository_id=1, title="Open 1", body="b", state="open", created_at=now, html_url="http://x")
    issue_open2 = Issue(id=2, issue_number=2, repository_id=1, title="Open 2", body="b", state="open", created_at=now, html_url="http://x")
    issue_closed = Issue(id=3, issue_number=3, repository_id=1, title="Closed 3", body="b", state="closed", created_at=now, html_url="http://x")

    # Runs
    run_recent = PipelineRun(
        id=10, pipeline_run_id="run_recent_1", ticket_id=1, status="SUCCEEDED",
        final_decision="AUTO_RESOLVE_RECOMMENDATION", calibrated_confidence=0.92,
        total_latency_ms=100.0, created_at=now
    )
    run_old = PipelineRun(
        id=11, pipeline_run_id="run_old_2", ticket_id=2, status="ESCALATED",
        final_decision="HUMAN_ESCALATION", calibrated_confidence=None,
        total_latency_ms=200.0, created_at=now - timedelta(hours=48)
    )
    run_unlinked = PipelineRun(
        id=12, pipeline_run_id="run_unlinked_3", ticket_id=None, status="SUCCEEDED",
        final_decision="AUTO_RESOLVE_RECOMMENDATION", calibrated_confidence=0.88,
        total_latency_ms=150.0, created_at=now
    )

    stage_high = PipelineStageRun(
        pipeline_run_id="run_recent_1", stage_name="classify_severity", status="SUCCEEDED",
        result_summary_json={"predicted_severity": "high"}
    )

    # Set up mock scalar / scalars behavior
    call_count = [0]
    def mock_scalar(stmt):
        call_count[0] += 1
        cnt = call_count[0]
        if cnt == 1:
            return 2  # open tickets
        elif cnt == 2:
            return 2  # 24h analyzed
        elif cnt == 3:
            return 2  # auto resolve
        elif cnt == 4:
            return 1  # human escalation
        elif cnt == 5:
            return 150.0  # avg latency
        return 0

    def mock_scalars(stmt):
        stmt_str = str(stmt).lower()
        mock_res = MagicMock()
        if "from severity_predictions" in stmt_str:
            mock_res.all.return_value = []
        elif "from pipeline_stage_runs" in stmt_str:
            mock_res.all.return_value = [stage_high]
        elif "from pipeline_runs" in stmt_str:
            mock_res.all.return_value = [run_recent, run_old, run_unlinked]
        else:
            mock_res.all.return_value = []
        return mock_res

    mock_session.scalar.side_effect = mock_scalar
    mock_session.scalars.side_effect = mock_scalars

    def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        # Test /summary
        res_sum = client.get("/api/v1/dashboard/summary")
        assert res_sum.status_code == 200
        data_sum = res_sum.json()
        assert data_sum["total_tickets"] == 2
        assert data_sum["analyzed_today"] == 2
        assert data_sum["auto_resolution_recommendations"] == 2
        assert data_sum["human_escalations"] == 1
        assert data_sum["high_severity_tickets"] == 1
        assert data_sum["average_pipeline_latency_ms"] == 150.0

        # Test /recent-runs
        res_runs = client.get("/api/v1/dashboard/recent-runs")
        assert res_runs.status_code == 200
        data_runs = res_runs.json()
        assert len(data_runs) == 3

        # Verify confidence: 0.92 for first run, None (null) for second run
        assert data_runs[0]["calibrated_confidence"] == 0.92
        assert data_runs[1]["calibrated_confidence"] is None

        # Verify unlinked run title and repo name
        assert data_runs[2]["title"] == "Standalone Pipeline Analysis"
        assert data_runs[2]["repository_name"] == "System Workspace"
    finally:
        app.dependency_overrides.clear()

