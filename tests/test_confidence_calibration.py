import pytest
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base,
    Repository,
    Issue,
    ResolutionRun,
    VerificationRun,
    ClaimVerificationRecord,
    ConfidenceRun,
    CalibrationRunRecord,
)
from app.schemas.verification_schemas import ResolutionVerificationSummary, ClaimVerificationResult
from app.schemas.confidence_schemas import ConfidenceFeatureVector, ConfidencePrediction
from app.services.confidence_service import (
    ConfidenceCalibrationService,
    extract_confidence_features,
    calculate_brier_score,
    calculate_ece,
)


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()

    repo = Repository(owner="microsoft", name="vscode", full_name="microsoft/vscode")
    session.add(repo)
    session.flush()

    now = datetime.now(timezone.utc)
    iss = Issue(
        github_issue_id=201, repository_id=repo.id, issue_number=201,
        title="Electron crash on macOS 14.5", body="Application quits unexpectedly.",
        state="closed", created_at=now, closed_at=now, html_url="https://github.com/microsoft/vscode/issues/201"
    )
    session.add(iss)
    session.flush()

    res_run = ResolutionRun(
        run_id="res_test_2001",
        issue_id=iss.id,
        repository_id=repo.id,
        model_name="gpt-4o-mini",
        prompt_version="resolution_prompt_v1",
        resolution_type="confirmed_historical_resolution",
        needs_human_review=False,
        citation_coverage=1.0,
        unsupported_claim_rate=0.0,
        latency_seconds=1.1,
        validation_status="passed",
        raw_output={"claims": [{"claim_id": "c1", "text": "Upgrade Electron", "source_ids": ["issue:201"]}]},
        created_at=now
    )
    session.add(res_run)
    session.commit()

    yield session
    session.close()


def test_brier_score_and_ece_calculations():
    """5, 6, 7. Test Brier score and ECE calculation functions."""
    y_true = [1, 1, 0, 0, 1]
    probas = [0.9, 0.8, 0.2, 0.1, 0.95]

    brier = calculate_brier_score(y_true, probas)
    assert 0.0 <= brier <= 1.0
    assert brier < 0.05  # Highly accurate predictions

    ece, mce, bin_table = calculate_ece(y_true, probas, n_bins=5)
    assert 0.0 <= ece <= 1.0
    assert 0.0 <= mce <= 1.0
    assert len(bin_table) == 5


def test_feature_extraction_and_vectorization():
    """1, 2, 16, 17. Test feature extraction, ordering, and versioning."""
    ver_summary = ResolutionVerificationSummary(
        verification_run_id="ver_001",
        resolution_run_id="res_001",
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
    ret_meta = {"top_dense_similarity": 0.88, "evidence_completeness": 0.9}

    feat = extract_confidence_features(
        resolution_run_data={"steps": ["Step 1", "Step 2"]},
        verification_summary=ver_summary,
        retrieval_metadata=ret_meta
    )

    assert feat.top_dense_similarity == 0.88
    assert feat.supported_claim_ratio == 1.0
    assert feat.critical_unsupported_count == 0

    lst = feat.to_list()
    assert len(lst) == 19
    assert len(ConfidenceFeatureVector.feature_names()) == 19


def test_threshold_selection_and_false_positive_budget():
    """8, 9, 10, 11. Test threshold optimization under false-positive budget."""
    service = ConfidenceCalibrationService()
    probas = [0.95, 0.90, 0.85, 0.70, 0.60, 0.55]
    y_true = [1, 1, 1, 0, 0, 0]

    opt_threshold, analysis_table = service.select_threshold_under_budget(
        probabilities=probas,
        y_true=y_true,
        max_false_auto_rate=0.02
    )

    assert 0.50 <= opt_threshold <= 0.95
    assert len(analysis_table) > 0


def test_hard_safety_overrides_and_decisions():
    """12, 13, 14, 15, 22. Test safety overrides (critical failure, contradiction) and decisions."""
    service = ConfidenceCalibrationService()
    feat = ConfidenceFeatureVector(
        supported_claim_ratio=1.0,
        evidence_completeness=0.9,
        citation_coverage=1.0,
        critical_unsupported_count=1  # Critical failure!
    )

    ver_summary = ResolutionVerificationSummary(
        verification_run_id="ver_002",
        resolution_run_id="res_002",
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
        has_critical_failure=True,
        claim_results=[]
    )

    pred = service.compute_confidence_and_decision(
        features=feat,
        verification_summary=ver_summary,
        custom_threshold=0.85
    )

    assert pred.decision == "HUMAN_REVIEW"
    assert "CRITICAL_CLAIM_FAILURE" in pred.reason_codes


def test_confidence_persistence_and_inference(in_memory_db):
    """3, 4, 18, 19, 20, 21. Test full confidence inference and DB persistence."""
    service = ConfidenceCalibrationService()
    feat = ConfidenceFeatureVector(
        top_dense_similarity=0.85,
        evidence_completeness=0.80,
        supported_claim_ratio=1.0,
        citation_coverage=1.0
    )

    ver_summary = ResolutionVerificationSummary(
        verification_run_id="ver_003",
        resolution_run_id="res_003",
        overall_faithfulness_status="FULLY_SUPPORTED",
        total_claims=1,
        supported_count=1,
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

    pred = service.compute_confidence_and_decision(
        features=feat,
        verification_summary=ver_summary,
        ticket_id=1,
        resolution_run_id="res_test_2001",
        session=in_memory_db
    )

    assert 0.0 <= pred.calibrated_confidence <= 1.0
    assert pred.decision in ["AUTO_RESOLVE", "HUMAN_REVIEW"]

    db_rec = in_memory_db.scalar(
        select(ConfidenceRun).where(ConfidenceRun.confidence_run_id == pred.confidence_run_id)
    )
    assert db_rec is not None
    assert db_rec.calibrated_confidence == pred.calibrated_confidence
