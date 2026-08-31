import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, PipelineRun, PipelineStageRun
from app.schemas.pipeline_schemas import TicketInput, PipelineGraphState, PipelineResult
from app.services.pipeline_orchestrator import (
    build_support_pipeline_graph,
    run_support_pipeline,
    replay_pipeline_run,
    router_after_retrieval,
    router_after_resolution,
    router_after_confidence,
    router_after_decision,
)


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def test_graph_construction():
    """1. Test LangGraph graph compilation."""
    app = build_support_pipeline_graph()
    assert app is not None


def test_input_validation():
    """20. Test ticket input validation."""
    with pytest.raises(ValueError):
        TicketInput(repository_id=1, title="")  # Empty title must fail


def test_conditional_routers():
    """13, 14, 15, 16, 17, 18, 19. Test conditional edge routing logic."""
    # Empty retrieval router
    state_empty_ret = {"insufficient_evidence": True, "retrieval_result": {"retrieved_cases": []}}
    assert router_after_retrieval(state_empty_ret) == "create_escalation_package"

    state_valid_ret = {"insufficient_evidence": False, "retrieval_result": {"retrieved_cases": [{"id": 1}]}}
    assert router_after_retrieval(state_valid_ret) == "generate_resolution"

    # Generation failure router
    state_gen_failed = {"stage_statuses": {"generate_resolution": "FAILED"}}
    assert router_after_resolution(state_gen_failed) == "create_escalation_package"

    # Verification / Confidence safety router
    state_ver_failed = {"verification_result": {"has_critical_failure": True, "contradicted_count": 0}}
    assert router_after_confidence(state_ver_failed) == "create_escalation_package"

    state_high_conf = {
        "verification_result": {"has_critical_failure": False, "contradicted_count": 0},
        "confidence_result": {"calibrated_confidence": 0.90, "threshold": 0.85}
    }
    assert router_after_confidence(state_high_conf) == "route_ticket"

    # Decision router
    state_auto_resolve = {"decision_result": {"final_decision": "AUTO_RESOLVE"}}
    assert router_after_decision(state_auto_resolve) == "finalize_pipeline"

    state_escalate = {"decision_result": {"final_decision": "HUMAN_REVIEW"}}
    assert router_after_decision(state_escalate) == "create_escalation_package"


@patch("app.services.pipeline_orchestrator.get_db")
def test_scenario_a_auto_resolve_recommendation(mock_get_db, in_memory_db):
    """Scenario A: Strong evidence + supported claims + high confidence + strong routing -> AUTO_RESOLVE_RECOMMENDATION."""
    mock_get_db.return_value.__enter__.return_value = in_memory_db

    ticket = TicketInput(repository_id=1, title="Integrated terminal pty crash on Windows", body="PowerShell exit 1")

    with patch("app.services.pipeline_orchestrator.SeverityClassifierService") as mock_sev_cls, \
         patch("app.services.pipeline_orchestrator.DuplicateDetector") as mock_dup_cls, \
         patch("app.services.pipeline_orchestrator.HybridRetrievalService") as mock_ret_cls, \
         patch("app.services.pipeline_orchestrator.GroundedResolutionService") as mock_gen_cls, \
         patch("app.services.pipeline_orchestrator.ClaimVerificationService") as mock_ver_cls, \
         patch("app.services.pipeline_orchestrator.ConfidenceCalibrationService") as mock_conf_cls, \
         patch("app.services.pipeline_orchestrator.RoutingEngineService") as mock_rout_cls, \
         patch("app.services.pipeline_orchestrator.DeterministicDecisionEngine") as mock_dec_cls:

        mock_sev_cls.return_value.predict_severity.return_value = {"predicted_label": "high", "prediction_score": 0.95, "model_name": "distilbert"}
        mock_dup_cls.return_value.detect_duplicate.return_value = {"is_duplicate": False, "cross_encoder_score": 0.10}
        mock_ret_cls.return_value.retrieve_resolved_cases.return_value = [{"issue_id": 101, "labels": ["area/terminal"]}]
        mock_gen_res = MagicMock()
        mock_gen_res.model_dump.return_value = {"summary": "Update terminal native pty dependencies.", "claims": []}
        mock_gen_cls.return_value.generate_resolution.return_value = (mock_gen_res, MagicMock(), "res_1")

        mock_ver_cls.return_value.verify_resolution.return_value = {
            "verification_run_id": "ver_1",
            "resolution_run_id": "res_1",
            "overall_faithfulness_status": "FULLY_SUPPORTED",
            "has_critical_failure": False,
            "contradicted_count": 0,
            "unsupported_count": 0,
            "supported_count": 2,
            "total_claims": 2,
            "citation_coverage": 1.0,
            "claim_support_rate": 1.0,
            "strict_faithfulness": 1.0,
            "unsupported_claim_rate": 0.0,
            "contradiction_rate": 0.0,
            "partial_support_rate": 0.0,
            "needs_human_review": False
        }

        mock_conf_cls.return_value.compute_confidence_and_decision.return_value = {
            "calibrated_confidence": 0.92, "decision": "AUTO_RESOLVE", "threshold": 0.85, "reason_codes": ["ALL_CLAIMS_SUPPORTED"]
        }

        mock_rout_cls.return_value.predict_route.return_value = {
            "predicted_component": "terminal", "predicted_team": "terminal-maintainers", "routing_probability": 0.90, "is_unknown_target": False, "is_low_support": False
        }

        mock_dec_cls.return_value.make_final_decision.return_value = {
            "final_decision": "AUTO_RESOLVE",
            "recommended_team": "terminal-maintainers",
            "recommended_component": "terminal",
            "reason_codes": ["ALL_CLAIMS_SUPPORTED"],
            "escalation_package_json": {}
        }

        res = run_support_pipeline(ticket)

        assert res.final_decision == "AUTO_RESOLVE_RECOMMENDATION"
        assert res.human_review_required is False
        assert res.status == "SUCCEEDED"
        assert res.total_latency_ms >= 0.0


@patch("app.services.pipeline_orchestrator.get_db")
def test_scenario_b_low_confidence_escalation(mock_get_db, in_memory_db):
    """Scenario B: Low calibrated confidence -> HUMAN_ESCALATION."""
    mock_get_db.return_value.__enter__.return_value = in_memory_db

    ticket = TicketInput(repository_id=1, title="Ambiguous error in editor", body="Something crashed")

    with patch("app.services.pipeline_orchestrator.SeverityClassifierService") as mock_sev_cls, \
         patch("app.services.pipeline_orchestrator.DuplicateDetector") as mock_dup_cls, \
         patch("app.services.pipeline_orchestrator.HybridRetrievalService") as mock_ret_cls, \
         patch("app.services.pipeline_orchestrator.GroundedResolutionService") as mock_gen_cls, \
         patch("app.services.pipeline_orchestrator.ClaimVerificationService") as mock_ver_cls, \
         patch("app.services.pipeline_orchestrator.ConfidenceCalibrationService") as mock_conf_cls:

        mock_sev_cls.return_value.predict_severity.return_value = {"predicted_label": "medium", "prediction_score": 0.50, "model_name": "distilbert"}
        mock_dup_cls.return_value.detect_duplicate.return_value = {"is_duplicate": False, "cross_encoder_score": 0.10}
        mock_ret_cls.return_value.retrieve_resolved_cases.return_value = [{"issue_id": 101}]
        mock_gen_res_b = MagicMock()
        mock_gen_res_b.model_dump.return_value = {"summary": "Unclear fix.", "claims": []}
        mock_gen_cls.return_value.generate_resolution.return_value = (mock_gen_res_b, MagicMock(), "res_2")
        mock_ver_cls.return_value.verify_resolution.return_value = {"has_critical_failure": False, "contradicted_count": 0, "overall_faithfulness_status": "MOSTLY_SUPPORTED"}
        mock_conf_cls.return_value.compute_confidence_and_decision.return_value = {"calibrated_confidence": 0.45, "decision": "HUMAN_REVIEW", "threshold": 0.85, "reason_codes": ["CONFIDENCE_BELOW_THRESHOLD"]}

        res = run_support_pipeline(ticket)

        assert res.final_decision == "HUMAN_ESCALATION"
        assert res.human_review_required is True
        assert res.status == "ESCALATED"


@patch("app.services.pipeline_orchestrator.get_db")
def test_scenario_c_critical_claim_contradicted(mock_get_db, in_memory_db):
    """Scenario C: Critical claim contradicted -> HUMAN_ESCALATION."""
    mock_get_db.return_value.__enter__.return_value = in_memory_db

    ticket = TicketInput(repository_id=1, title="Editor memory leak", body="RAM spikes to 16GB")

    with patch("app.services.pipeline_orchestrator.SeverityClassifierService") as mock_sev_cls, \
         patch("app.services.pipeline_orchestrator.DuplicateDetector") as mock_dup_cls, \
         patch("app.services.pipeline_orchestrator.HybridRetrievalService") as mock_ret_cls, \
         patch("app.services.pipeline_orchestrator.GroundedResolutionService") as mock_gen_cls, \
         patch("app.services.pipeline_orchestrator.ClaimVerificationService") as mock_ver_cls:

        mock_sev_cls.return_value.predict_severity.return_value = {"predicted_label": "high", "prediction_score": 0.90, "model_name": "distilbert"}
        mock_dup_cls.return_value.detect_duplicate.return_value = {"is_duplicate": False, "cross_encoder_score": 0.10}
        mock_ret_cls.return_value.retrieve_resolved_cases.return_value = [{"issue_id": 101}]
        mock_gen_res_c = MagicMock()
        mock_gen_res_c.model_dump.return_value = {"summary": "Incorrect claim made.", "claims": []}
        mock_gen_cls.return_value.generate_resolution.return_value = (mock_gen_res_c, MagicMock(), "res_3")
        mock_ver_cls.return_value.verify_resolution.return_value = {"has_critical_failure": True, "contradicted_count": 1, "overall_faithfulness_status": "NEEDS_HUMAN_REVIEW"}

        res = run_support_pipeline(ticket)

        assert res.final_decision == "HUMAN_ESCALATION"
        assert res.human_review_required is True


@patch("app.services.pipeline_orchestrator.get_db")
def test_scenario_d_empty_retrieval(mock_get_db, in_memory_db):
    """Scenario D: Zero retrieved cases -> HUMAN_ESCALATION (NO_RESOLUTION_EVIDENCE)."""
    mock_get_db.return_value.__enter__.return_value = in_memory_db

    ticket = TicketInput(repository_id=1, title="Completely unknown error xyz12345")

    with patch("app.services.pipeline_orchestrator.SeverityClassifierService") as mock_sev_cls, \
         patch("app.services.pipeline_orchestrator.DuplicateDetector") as mock_dup_cls, \
         patch("app.services.pipeline_orchestrator.HybridRetrievalService") as mock_ret_cls:

        mock_sev_cls.return_value.predict_severity.return_value = {"predicted_label": "medium", "prediction_score": 0.50, "model_name": "distilbert"}
        mock_dup_cls.return_value.detect_duplicate.return_value = {"is_duplicate": False, "cross_encoder_score": 0.10}
        mock_ret_cls.return_value.retrieve_resolved_cases.return_value = []

        res = run_support_pipeline(ticket)

        assert res.final_decision == "HUMAN_ESCALATION"
        assert "NO_RESOLUTION_EVIDENCE" in res.escalation_package.get("reason_codes", [])


@patch("app.services.pipeline_orchestrator.get_db")
def test_replay_pipeline_capability(mock_get_db, in_memory_db):
    """25. Test read-only pipeline replay capability from DB."""
    mock_get_db.return_value.__enter__.return_value = in_memory_db

    pipeline_id = "pipeline_test_replay_123"
    run_rec = PipelineRun(
        pipeline_run_id=pipeline_id,
        ticket_id=1,
        status="SUCCEEDED",
        final_decision="AUTO_RESOLVE_RECOMMENDATION",
        recommended_team="terminal-maintainers",
        calibrated_confidence=0.90,
        routing_probability=0.88,
        total_latency_ms=125.0,
        created_at=datetime.now(timezone.utc)
    )
    in_memory_db.add(run_rec)

    stage_rec = PipelineStageRun(
        pipeline_run_id=pipeline_id,
        stage_name="initialize_ticket",
        status="SUCCEEDED",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        latency_ms=10.0
    )
    in_memory_db.add(stage_rec)
    in_memory_db.commit()

    replayed = replay_pipeline_run(pipeline_id)
    assert replayed is not None
    assert replayed.pipeline_run_id == pipeline_id
    assert replayed.final_decision == "AUTO_RESOLVE_RECOMMENDATION"
    assert replayed.stage_statuses.get("initialize_ticket") == "SUCCEEDED"
