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
    IssueEmbedding,
    ResolutionRun,
    ResolutionClaimRecord,
)
from app.schemas.resolution_schemas import (
    ResolutionRequest,
    EvidenceCase,
    EvidencePackage,
    ResolutionResponse,
    ResolutionStep,
    ResolutionClaim,
)
from app.services.embedding_service import EmbeddingService
from app.services.hybrid_retrieval_service import HybridRetrievalService
from app.services.llm_client import LLMClient
from app.services.grounded_resolution_service import (
    GroundedResolutionService,
    calculate_case_completeness,
    prioritize_case_context,
)
from scripts.evaluate_resolution_generation import compute_cosine_similarity


@pytest.fixture
def mock_embedding_service():
    mock_svc = MagicMock(spec=EmbeddingService)
    mock_svc.model_name = "BAAI/bge-small-en-v1.5"
    mock_svc.generate_text_embedding.return_value = [0.1] * 384
    return mock_svc


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
    past_10d = now - timedelta(days=10)
    past_5d = now - timedelta(days=5)

    # Historical Issue 101 with closing comment & PR
    iss1 = Issue(
        github_issue_id=101, repository_id=repo.id, issue_number=101,
        title="Terminal window crashes with ERR_CONNECTION_RESET",
        body="Terminal exits immediately with exit code 1.",
        state="closed", created_at=past_10d, closed_at=past_5d, html_url="https://github.com/microsoft/vscode/issues/101"
    )
    comm1 = Comment(issue_id=1, body="Fixed in PR #500. Updated OAuth2 token handling.", created_at=past_5d)
    pr1 = PullRequest(repository_id=repo.id, pr_number=500, html_url="https://github.com/microsoft/vscode/pull/500")
    iss1.comments.append(comm1)
    iss1.pull_requests.append(pr1)

    # Historical Issue 102
    iss2 = Issue(
        github_issue_id=102, repository_id=repo.id, issue_number=102,
        title="NullPointerException in editor panel",
        body="Occurs when switching tabs rapidly.",
        state="closed", created_at=past_10d, closed_at=past_5d, html_url="https://github.com/microsoft/vscode/issues/102"
    )

    session.add_all([iss1, iss2])
    session.flush()

    np.random.seed(42)
    for iss in [iss1, iss2]:
        vec = np.random.randn(384).astype(np.float32)
        vec = (vec / np.linalg.norm(vec)).tolist()
        emb = IssueEmbedding(
            issue_id=iss.id,
            model_name="BAAI/bge-small-en-v1.5",
            embedding=vec
        )
        session.add(emb)

    session.commit()
    yield session
    session.close()


def test_evidence_completeness_and_prioritization():
    """1, 2, 3. Test completeness indicator, prioritization, and truncation."""
    completeness = calculate_case_completeness(
        has_body=True, has_comments=True, has_closing_comment=True, has_prs=True, has_resolution_text=True
    )
    assert completeness == 1.0

    prob, res, truncated = prioritize_case_context(
        title="Sample Title",
        body="Sample Body",
        comments=["Fixed in PR #500", "Regular comment"],
        pr_info=[{"number": 500, "title": "Fix bug"}],
        max_chars=100
    )
    assert "CLOSING COMMENT:" in res
    assert truncated is True


def test_grounded_resolution_success_flow(in_memory_db, mock_embedding_service, tmp_path):
    """4, 9, 10, 11, 14, 19, 20, 21, 22. Test resolution flow with mock LLM."""
    retrieval_svc = HybridRetrievalService(
        embedding_service=mock_embedding_service, db_session=in_memory_db, bm25_index_dir=str(tmp_path)
    )
    retrieval_svc.load_or_build_bm25_index(in_memory_db, force_rebuild=True)

    llm_client = LLMClient()
    mock_llm_dict = {
        "summary": "Terminal crash issue is resolved by updating OAuth2 token refresh logic.",
        "diagnosis": "Connection resets due to invalid OAuth2 token refresh.",
        "recommended_resolution": "Apply patch from PR #500 to update OAuth2 token refresh logic.",
        "resolution_type": "confirmed_historical_resolution",
        "steps": [
            {
                "step": 1,
                "instruction": "Upgrade terminal module to v2.4.1",
                "source_ids": ["issue:101", "pr:500"]
            }
        ],
        "claims": [
            {
                "claim_id": "c1",
                "text": "Terminal connection resets were caused by OAuth2 token refresh failure.",
                "source_ids": ["issue:101"]
            }
        ],
        "limitations": ["Applies only to terminal panel"],
        "needs_human_review": True,
        "citation_coverage": 1.0,
        "unsupported_claim_rate": 0.0
    }
    llm_client.set_mock_response(mock_llm_dict)

    service = GroundedResolutionService(
        retrieval_service=retrieval_svc,
        llm_client=llm_client,
        db_session=in_memory_db
    )

    request = ResolutionRequest(
        title="Terminal window crashes with ERR_CONNECTION_RESET",
        body="Terminal exits immediately with exit code 1.",
        repository_id=1,
        issue_number=101
    )

    response, evidence_pkg, run_id = service.generate_resolution(request, in_memory_db)

    assert response.resolution_type == "confirmed_historical_resolution"
    assert response.citation_coverage == 1.0
    assert response.unsupported_claim_rate == 0.0
    assert len(response.steps) == 1
    assert response.steps[0].source_ids == ["issue:101", "pr:500"]

    # Verify DB persistence
    db_run = in_memory_db.scalar(select(ResolutionRun).where(ResolutionRun.run_id == run_id))
    assert db_run is not None
    assert db_run.resolution_type == "confirmed_historical_resolution"

    claims_recs = in_memory_db.scalars(
        select(ResolutionClaimRecord).where(ResolutionClaimRecord.resolution_run_id == db_run.id)
    ).all()
    assert len(claims_recs) == 1
    assert claims_recs[0].verification_status == "pending"


def test_invalid_source_id_and_unsupported_claim_detection(in_memory_db, mock_embedding_service, tmp_path):
    """7, 8. Test invalid source IDs and unsupported claims detection."""
    retrieval_svc = HybridRetrievalService(
        embedding_service=mock_embedding_service, db_session=in_memory_db, bm25_index_dir=str(tmp_path)
    )
    retrieval_svc.load_or_build_bm25_index(in_memory_db, force_rebuild=True)

    llm_client = LLMClient()
    mock_llm_dict = {
        "summary": "Summary text",
        "diagnosis": "Diagnosis text",
        "recommended_resolution": "Resolution text",
        "resolution_type": "evidence_based_recommendation",
        "steps": [],
        "claims": [
            {
                "claim_id": "c1",
                "text": "Fabricated claim referencing fake issue",
                "source_ids": ["issue:999999"]
            }
        ],
        "limitations": [],
        "needs_human_review": True,
        "citation_coverage": 0.0,
        "unsupported_claim_rate": 1.0
    }
    llm_client.set_mock_response(mock_llm_dict)

    service = GroundedResolutionService(
        retrieval_service=retrieval_svc,
        llm_client=llm_client,
        db_session=in_memory_db
    )

    request = ResolutionRequest(
        title="Terminal window crashes",
        body="Details here",
        repository_id=1
    )

    response, evidence_pkg, run_id = service.generate_resolution(request, in_memory_db)

    assert response.unsupported_claim_rate == 1.0
    assert response.citation_coverage == 0.0
    assert response.needs_human_review is True
    assert "invalid_references" in response.claims[0].source_validation_status


def test_llm_timeout_and_fallback_behavior(in_memory_db, mock_embedding_service, tmp_path):
    """5, 6, 12, 13, 15, 38. Test LLM failure / missing API key fallback."""
    retrieval_svc = HybridRetrievalService(
        embedding_service=mock_embedding_service, db_session=in_memory_db, bm25_index_dir=str(tmp_path)
    )
    retrieval_svc.load_or_build_bm25_index(in_memory_db, force_rebuild=True)
    llm_client = LLMClient(max_retries=1)
    with patch.object(llm_client, "_call_openai_api", side_effect=RuntimeError("LLM API Timeout")):
        service = GroundedResolutionService(
            retrieval_service=retrieval_svc, llm_client=llm_client, db_session=in_memory_db
        )
        request = ResolutionRequest(title="Random unknown bug", body="No info")

        response, evidence_pkg, run_id = service.generate_resolution(request, in_memory_db)

        assert response.resolution_type == "insufficient_evidence"
        assert response.needs_human_review is True


def test_semantic_similarity_calculation():
    """18. Test semantic similarity function."""
    v1 = [0.1, 0.2, 0.3]
    v2 = [0.1, 0.2, 0.3]
    v3 = [-0.1, -0.2, -0.3]

    assert abs(compute_cosine_similarity(v1, v2) - 1.0) < 1e-5
    assert abs(compute_cosine_similarity(v1, v3) - (-1.0)) < 1e-5
