import pytest
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base,
    Repository,
    Issue,
    ResolutionRun,
    VerificationRun,
    ConfidenceRun,
    RoutingTarget,
    RoutingPrediction,
    DecisionRun,
)
from app.schemas.verification_schemas import ResolutionVerificationSummary
from app.schemas.confidence_schemas import ConfidencePrediction, ConfidenceFeatureVector
from app.schemas.routing_schemas import RoutingResult, TopKRoutingCandidate
from app.services.routing_service import (
    RoutingEngineService,
    extract_component_from_labels,
    map_component_to_team,
)
from app.services.decision_service import DeterministicDecisionEngine


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()

    repo = Repository(owner="microsoft", name="vscode", full_name="microsoft/vscode")
    session.add(repo)
    session.flush()

    target1 = RoutingTarget(
        routing_target_id="component:terminal",
        repository_id=repo.id,
        component="terminal",
        team="terminal-maintainers",
        historical_issue_count=50,
        created_at=datetime.now(timezone.utc)
    )
    session.add(target1)

    target2 = RoutingTarget(
        routing_target_id="component:obscure_module",
        repository_id=repo.id,
        component="obscure_module",
        team="obscure-team",
        historical_issue_count=1,  # Low support! (< 3)
        created_at=datetime.now(timezone.utc)
    )
    session.add(target2)
    session.commit()

    yield session
    session.close()


def test_component_label_extraction_and_filtering():
    """1, 2, 3. Test component label extraction, non-component label filtering, multi-label handling."""
    labels = ["bug", "priority-p1", "area/terminal", "verified"]
    comp = extract_component_from_labels(labels)
    assert comp == "terminal"

    team = map_component_to_team(comp)
    assert team == "terminal-maintainers"


def test_baseline_retrieval_routing():
    """4, 6, 7. Test baseline retrieval component majority router."""
    service = RoutingEngineService()
    retrieved = [
        {"labels": ["area/terminal"]},
        {"labels": ["area/terminal"]},
        {"labels": ["area/editor"]}
    ]
    candidates = service.baseline_retrieval_routing(retrieved)
    assert len(candidates) >= 2
    assert candidates[0].component == "terminal"
    assert candidates[0].probability == round(2.0 / 3.0, 4)


def test_low_support_and_unknown_components(in_memory_db):
    """9, 10, 11. Test low-support (< 3 samples) and unknown component handling."""
    service = RoutingEngineService()

    # Unknown component
    res_unknown = service.predict_route(
        retrieved_cases=[{"labels": ["area/unseen_custom_comp"]}],
        session=in_memory_db
    )
    assert res_unknown.is_unknown_target is True
    assert res_unknown.predicted_team == "GENERAL_SUPPORT_QUEUE"

    # Low support component
    res_low = service.predict_route(
        retrieved_cases=[{"labels": ["obscure_module"]}],
        session=in_memory_db
    )
    assert res_low.is_low_support is True
    assert res_low.predicted_team == "GENERAL_SUPPORT_QUEUE"


def test_decision_hierarchy_safety_overrides():
    """12, 15, 16, 17, 18, 20, 21, 22. Test safety precedence overrides."""
    engine = DeterministicDecisionEngine()

    # Critical Verification Failure -> Escalates or Human Review
    ver_failed = ResolutionVerificationSummary(
        verification_run_id="ver_99",
        resolution_run_id="res_99",
        overall_faithfulness_status="NEEDS_HUMAN_REVIEW",
        total_claims=1,
        supported_count=0,
        partially_supported_count=0,
        unsupported_count=1,
        contradicted_count=0,
        unclear_count=0,
        citation_coverage=0.0,
        claim_support_rate=0.0,
        strict_faithfulness=0.0,
        unsupported_claim_rate=1.0,
        contradiction_rate=0.0,
        partial_support_rate=0.0,
        needs_human_review=True,
        has_critical_failure=True,  # Critical failure!
        claim_results=[]
    )

    dec_res = engine.make_final_decision(
        ticket_id=1,
        severity_level="high",
        verification_summary=ver_failed
    )

    assert dec_res.final_decision == "ESCALATE_HIGH_RISK"
    assert "CRITICAL_CLAIM_FAILURE" in dec_res.reason_codes


def test_auto_resolve_eligibility():
    """19, 23, 25. Test AUTO_RESOLVE eligibility when all safety checks pass."""
    engine = DeterministicDecisionEngine()

    ver_success = ResolutionVerificationSummary(
        verification_run_id="ver_100",
        resolution_run_id="res_100",
        overall_faithfulness_status="FULLY_SUPPORTED",
        total_claims=2,
        supported_count=2,
        partially_supported_count=0,
        unsupported_count=0,
        contradicted_count=0,
        unclear_count=0,
        citation_coverage=1.0,
        claim_support_rate=1.0,
        strict_faithfulness=1.0,
        unsupported_claim_rate=0.0,
        contradiction_rate=0.0,
        partial_support_rate=0.0,
        needs_human_review=False,
        has_critical_failure=False,
        claim_results=[]
    )

    conf_success = ConfidencePrediction(
        confidence_run_id="conf_100",
        ticket_id=1,
        calibrated_confidence=0.92,
        decision="AUTO_RESOLVE",
        threshold=0.85,
        reason_codes=["ALL_CLAIMS_SUPPORTED"],
        model_version="confidence_model_v1",
        feature_version="features_v1",
        threshold_version="threshold_v1",
        features=ConfidenceFeatureVector(supported_claim_ratio=1.0)
    )

    routing_success = RoutingResult(
        routing_prediction_id="route_100",
        predicted_component="terminal",
        predicted_team="terminal-maintainers",
        routing_probability=0.85,
        model_version="routing_model_v1"
    )

    dec_res = engine.make_final_decision(
        ticket_id=1,
        severity_level="medium",
        retrieved_cases=[{"issue_id": 1, "labels": ["area/terminal"]}],
        verification_summary=ver_success,
        confidence_pred=conf_success,
        routing_res=routing_success
    )

    assert dec_res.final_decision == "AUTO_RESOLVE"
    assert "HIGH_CONFIDENCE_VERIFIED" in dec_res.reason_codes
    assert dec_res.recommended_team == "terminal-maintainers"
    assert dec_res.escalation_package is not None
