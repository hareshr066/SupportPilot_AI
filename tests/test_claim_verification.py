import pytest
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base,
    Repository,
    Issue,
    Comment,
    PullRequest,
    ResolutionRun,
    ResolutionClaimRecord,
    VerificationRun,
    ClaimVerificationRecord,
)
from app.schemas.verification_schemas import (
    EvidenceSpan,
    ClaimVerificationResult,
    ResolutionVerificationSummary,
)
from app.services.llm_client import LLMClient
from app.services.claim_verification_service import (
    ClaimVerificationService,
    decompose_claim,
    classify_claim_criticality,
    extract_relevant_evidence_snippets,
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
    past_5d = now - timedelta(days=5)

    # Issue 101 with closing comment & PR
    iss1 = Issue(
        github_issue_id=101, repository_id=repo.id, issue_number=101,
        title="Terminal window crashes with ERR_CONNECTION_RESET",
        body="Terminal exits immediately with exit code 1.",
        state="closed", created_at=past_5d, closed_at=past_5d, html_url="https://github.com/microsoft/vscode/issues/101"
    )
    comm1 = Comment(issue_id=1, body="Fixed in PR #500. Upgrade to v2.4.1 to apply patch.", created_at=past_5d)
    pr1 = PullRequest(repository_id=repo.id, pr_number=500, html_url="https://github.com/microsoft/vscode/pull/500")
    iss1.comments.append(comm1)
    iss1.pull_requests.append(pr1)

    session.add(iss1)
    session.flush()

    res_run = ResolutionRun(
        run_id="res_test_1001",
        issue_id=iss1.id,
        repository_id=repo.id,
        model_name="gpt-4o-mini",
        prompt_version="resolution_prompt_v1",
        resolution_type="confirmed_historical_resolution",
        needs_human_review=False,
        citation_coverage=1.0,
        unsupported_claim_rate=0.0,
        latency_seconds=1.2,
        validation_status="passed",
        raw_output={},
        created_at=now
    )
    session.add(res_run)
    session.flush()

    c1 = ResolutionClaimRecord(
        claim_id="c1",
        resolution_run_id=res_run.id,
        claim_text="Terminal crash was resolved by PR #500 and requires upgrade to v2.4.1.",
        source_ids=["issue:101", "pr:500"],
        source_validation_status="valid",
        verification_status="pending",
        created_at=now
    )
    c2 = ResolutionClaimRecord(
        claim_id="c2",
        resolution_run_id=res_run.id,
        claim_text="Run sudo rm -rf /etc/vscode to reset configuration.",
        source_ids=["issue:101"],
        source_validation_status="valid",
        verification_status="pending",
        created_at=now
    )
    session.add_all([c1, c2])
    session.commit()

    yield session
    session.close()


def test_claim_decomposition_and_criticality():
    """1, 4, 10, 11. Test claim decomposition and criticality classification."""
    comp_claim = "The bug affects Windows and Linux and was fixed in v2.4.1."
    decomposed = decompose_claim("c1", comp_claim)
    assert len(decomposed) == 2
    assert decomposed[0][0] == "c1_a"
    assert decomposed[1][0] == "c1_b"

    is_crit, is_dest = classify_claim_criticality("Upgrade to v2.4.1 to fix diagnosis.")
    assert is_crit is True
    assert is_dest is False

    is_crit_d, is_dest_d = classify_claim_criticality("Run sudo rm -rf /var/data")
    assert is_dest_d is True


def test_evidence_snippet_extraction():
    """13. Test snippet extraction from source content."""
    content = "Sentence one is about terminal. Sentence two discusses OAuth token. Sentence three mentions release v2.4.1."
    snippets = extract_relevant_evidence_snippets("release v2.4.1", "issue:101", content, top_k=2)
    assert len(snippets) > 0
    assert "v2.4.1" in snippets[0].text


def test_verify_single_claim_supported_and_unsupported(in_memory_db):
    """2, 3, 4, 8, 16, 17. Test single claim verification logic."""
    llm_client = LLMClient()
    mock_llm_dict = {
        "verdict": "SUPPORTED",
        "support_strength": 0.95,
        "explanation": "Evidence explicitly states fix in PR #500 and v2.4.1.",
        "evidence_spans": [{"source_id": "issue:101", "text": "Fixed in PR #500", "relevance_score": 0.9}]
    }
    llm_client.set_mock_response(mock_llm_dict)

    service = ClaimVerificationService(verifier_llm_client=llm_client, db_session=in_memory_db)
    resolved_sources = service.batch_fetch_sources(["issue:101", "pr:500"], in_memory_db)

    res = service.verify_single_claim(
        claim_id="c1",
        parent_claim_id=None,
        claim_text="Fixed in PR #500",
        source_ids=["issue:101", "pr:500"],
        resolved_sources=resolved_sources
    )

    assert res.verdict == "SUPPORTED"
    assert res.support_strength == 0.95


def test_verify_single_claim_invalid_source():
    """2, 7. Test behavior when source ID is invalid or missing."""
    service = ClaimVerificationService()
    res = service.verify_single_claim(
        claim_id="c1",
        parent_claim_id=None,
        claim_text="Some claim",
        source_ids=["issue:999999"],
        resolved_sources={}
    )

    assert res.verdict == "UNCLEAR"
    assert res.support_strength == 0.0


def test_full_resolution_verification_pipeline(in_memory_db):
    """5, 6, 9, 10, 11, 14, 15, 16, 18, 19, 20. Test complete resolution verification."""
    llm_client = LLMClient()
    mock_llm_dict = {
        "verdict": "SUPPORTED",
        "support_strength": 0.9,
        "explanation": "Verified against source text.",
        "evidence_spans": []
    }
    llm_client.set_mock_response(mock_llm_dict)

    service = ClaimVerificationService(verifier_llm_client=llm_client, db_session=in_memory_db)
    summary = service.verify_resolution("res_test_1001", in_memory_db)

    assert summary.total_claims > 0
    assert summary.verification_run_id.startswith("ver_")
    assert summary.overall_faithfulness_status in ["FULLY_SUPPORTED", "MOSTLY_SUPPORTED", "NEEDS_HUMAN_REVIEW", "CONTRADICTED"]

    # Verify DB Persistence
    db_ver_run = in_memory_db.scalar(
        select(VerificationRun).where(VerificationRun.verification_run_id == summary.verification_run_id)
    )
    assert db_ver_run is not None
    assert db_ver_run.total_claims == summary.total_claims

    db_claims = in_memory_db.scalars(
        select(ClaimVerificationRecord).where(ClaimVerificationRecord.verification_run_id == db_ver_run.id)
    ).all()
    assert len(db_claims) == summary.total_claims
