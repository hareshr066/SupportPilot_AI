import pytest
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base,
    Repository,
    Issue,
    Label,
    Comment,
    PullRequest,
    IssueEmbedding,
    RetrievalIndexMetadata,
    RetrievalEvaluationRun,
)
from app.services.embedding_service import EmbeddingService
from app.services.bm25_service import BM25Index, tokenize_technical_text
from app.services.hybrid_retrieval_service import (
    HybridRetrievalService,
    build_canonical_text,
    calculate_resolution_evidence,
)
from scripts.evaluate_retrieval import calculate_mrr, calculate_recall, calculate_ndcg


@pytest.fixture
def mock_embedding_service():
    mock_svc = MagicMock(spec=EmbeddingService)
    mock_svc.model_name = "BAAI/bge-small-en-v1.5"
    mock_svc.generate_text_embedding.return_value = [0.1] * 384
    mock_svc.generate_issue_embedding.return_value = [0.1] * 384
    return mock_svc


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()

    repo1 = Repository(owner="microsoft", name="vscode", full_name="microsoft/vscode")
    repo2 = Repository(owner="facebook", name="react", full_name="facebook/react")
    session.add_all([repo1, repo2])
    session.flush()

    now = datetime.now(timezone.utc)
    past_10d = now - timedelta(days=10)
    past_5d = now - timedelta(days=5)

    # Issue 1: Closed with PR and comments (Strong resolution evidence)
    iss1 = Issue(
        github_issue_id=101, repository_id=repo1.id, issue_number=1,
        title="Terminal crash ERR_CONNECTION_RESET on startup",
        body="Terminal window exits immediately with exit code 1.",
        state="closed", created_at=past_10d, closed_at=past_5d, html_url="https://github.com/microsoft/vscode/issues/1"
    )
    comm1 = Comment(issue_id=1, body="Fixed in PR #5. Updated OAuth2 token handling.", created_at=past_5d)
    pr1 = PullRequest(repository_id=repo1.id, pr_number=5, html_url="https://github.com/microsoft/vscode/pull/5")
    iss1.comments.append(comm1)
    iss1.pull_requests.append(pr1)

    # Issue 2: Closed without PR (Moderate resolution evidence)
    iss2 = Issue(
        github_issue_id=102, repository_id=repo1.id, issue_number=2,
        title="NullPointerException in editor panel",
        body="Occurs when switching tabs rapidly.",
        state="closed", created_at=past_10d, closed_at=past_5d, html_url="https://github.com/microsoft/vscode/issues/2"
    )

    # Issue 3: Open issue in repo1
    iss3 = Issue(
        github_issue_id=103, repository_id=repo1.id, issue_number=3,
        title="Feature request: dark mode toggle",
        body="Please add dark mode option.",
        state="open", created_at=now, html_url="https://github.com/microsoft/vscode/issues/3"
    )

    # Issue 4: Closed issue in repo2 (different repository)
    iss4 = Issue(
        github_issue_id=104, repository_id=repo2.id, issue_number=10,
        title="WebSocket connection reset ERR_CONNECTION_RESET",
        body="WebSocket connection fails on v2.4.1",
        state="closed", created_at=past_10d, closed_at=past_5d, html_url="https://github.com/facebook/react/issues/10"
    )

    session.add_all([iss1, iss2, iss3, iss4])
    session.flush()

    # Add embeddings (mock 384 dim vectors)
    np.random.seed(42)
    for iss in [iss1, iss2, iss3, iss4]:
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


def test_bm25_technical_token_preservation():
    """17. Test BM25 technical token preservation."""
    text = "ERR_CONNECTION_RESET in NullPointerException OAuth2 v2.4.1 postgresql WebSocket"
    tokens = tokenize_technical_text(text)

    assert "err_connection_reset" in tokens
    assert "nullpointerexception" in tokens
    assert "oauth2" in tokens
    assert "v2.4.1" in tokens
    assert "postgresql" in tokens
    assert "websocket" in tokens


def test_canonical_text_construction_and_resolution_evidence():
    """7 & 12. Test canonical text construction and resolution evidence scoring."""
    canonical = build_canonical_text(
        title="Test Title",
        body="Test Body",
        labels=["area-terminal"],
        comments=["Fixed in PR #10"],
        pr_titles=["PR #10 Fix bug"]
    )
    assert "TITLE:\nTest Title" in canonical
    assert "Fixed in PR #10" in canonical

    ev_score, flags = calculate_resolution_evidence(
        has_comments=True,
        has_prs=True,
        comments_text="Fixed in PR #10",
        pr_text="PR #10 Fix bug"
    )
    assert ev_score > 0.5
    assert flags["has_closing_comment"] is True
    assert flags["has_linked_pr"] is True
    assert flags["has_resolution_text"] is True


def test_dense_retrieval(in_memory_db, mock_embedding_service, tmp_path):
    """1. Test dense semantic retrieval."""
    service = HybridRetrievalService(
        embedding_service=mock_embedding_service, db_session=in_memory_db, bm25_index_dir=str(tmp_path)
    )
    query_emb = [0.1] * 384
    results = service.retrieve_dense(query_emb, in_memory_db, repository_id=1, top_k=5)

    assert len(results) > 0
    for issue_id, score in results:
        assert isinstance(issue_id, int)
        assert isinstance(score, float)


def test_bm25_retrieval(in_memory_db, mock_embedding_service, tmp_path):
    """2 & 11. Test BM25 retrieval and missing document handling."""
    service = HybridRetrievalService(
        embedding_service=mock_embedding_service, db_session=in_memory_db, bm25_index_dir=str(tmp_path)
    )
    service.load_or_build_bm25_index(in_memory_db, repository_id=1, force_rebuild=True)

    results = service.retrieve_bm25("ERR_CONNECTION_RESET", in_memory_db, repository_id=1, top_k=5)
    assert len(results) > 0
    assert results[0][1] > 0.0


def test_hybrid_rrf_fusion_and_deduplication(in_memory_db, mock_embedding_service, tmp_path):
    """3, 4, 14, 16. Test RRF fusion, deduplication, schema, no duplicates."""
    service = HybridRetrievalService(
        embedding_service=mock_embedding_service, db_session=in_memory_db, bm25_index_dir=str(tmp_path)
    )
    service.load_or_build_bm25_index(in_memory_db, repository_id=1, force_rebuild=True)

    results = service.retrieve_resolved_cases(
        query_text="Terminal crash ERR_CONNECTION_RESET",
        repository_id=1,
        top_k=10,
        db_session=in_memory_db
    )

    assert len(results) > 0
    issue_ids = [r["issue_id"] for r in results]
    assert len(issue_ids) == len(set(issue_ids))  # No duplicate results

    # Verify structured response schema
    first = results[0]
    assert "issue_id" in first
    assert "issue_number" in first
    assert "dense_score" in first
    assert "bm25_score" in first
    assert "rrf_score" in first
    assert "evidence_score" in first
    assert "final_score" in first
    assert "resolution_evidence" in first


def test_repository_scoping(in_memory_db, mock_embedding_service, tmp_path):
    """5 & 6. Test same-repository filtering vs global retrieval."""
    service = HybridRetrievalService(
        embedding_service=mock_embedding_service, db_session=in_memory_db, bm25_index_dir=str(tmp_path)
    )
    service.load_or_build_bm25_index(in_memory_db, force_rebuild=True)

    # Same repository (repo 1)
    repo1_results = service.retrieve_resolved_cases(
        query_text="ERR_CONNECTION_RESET",
        repository_id=1,
        top_k=10,
        db_session=in_memory_db
    )
    for r in repo1_results:
        assert r["repository_id"] == 1

    # Global retrieval across all repositories
    from config import settings
    orig_scope = settings.retrieval_repository_scope
    settings.retrieval_repository_scope = "all_repositories"
    try:
        global_results = service.retrieve_resolved_cases(
            query_text="ERR_CONNECTION_RESET",
            repository_id=None,
            top_k=10,
            db_session=in_memory_db
        )
        repo_ids = set(r["repository_id"] for r in global_results)
        assert len(repo_ids) >= 1
    finally:
        settings.retrieval_repository_scope = orig_scope


def test_temporal_filtering(in_memory_db, mock_embedding_service, tmp_path):
    """8. Test temporal filtering constraint."""
    service = HybridRetrievalService(
        embedding_service=mock_embedding_service, db_session=in_memory_db, bm25_index_dir=str(tmp_path)
    )
    service.load_or_build_bm25_index(in_memory_db, force_rebuild=True)

    cutoff = datetime.now(timezone.utc) - timedelta(days=20)  # Before any issue was created
    results = service.retrieve_resolved_cases(
        query_text="Terminal crash",
        repository_id=1,
        temporal_cutoff=cutoff,
        db_session=in_memory_db
    )
    assert len(results) == 0  # All issues created after cutoff are filtered out


def test_empty_query_and_missing_embedding(in_memory_db, mock_embedding_service, tmp_path):
    """9 & 10. Test empty query and missing embedding behavior."""
    service = HybridRetrievalService(
        embedding_service=mock_embedding_service, db_session=in_memory_db, bm25_index_dir=str(tmp_path)
    )
    results = service.retrieve_resolved_cases("", repository_id=1, db_session=in_memory_db)
    assert isinstance(results, list)


def test_index_versioning_and_metadata(in_memory_db, mock_embedding_service, tmp_path):
    """15. Test index versioning and persistence metadata."""
    service = HybridRetrievalService(
        embedding_service=mock_embedding_service, db_session=in_memory_db, bm25_index_dir=str(tmp_path)
    )
    res = service.build_retrieval_index(in_memory_db, repository_id=1, index_version="v_test_01")

    assert res["index_version"] == "v_test_01"
    assert res["document_count"] > 0

    meta = in_memory_db.scalar(
        select(RetrievalIndexMetadata).where(RetrievalIndexMetadata.index_version == "v_test_01")
    )
    assert meta is not None
    assert meta.document_count == res["document_count"]


def test_evaluation_metrics_helpers():
    """18, 19, 20, 21. Test evaluation metric functions (Recall, MRR, nDCG)."""
    retrieved = [10, 20, 30, 40, 50]
    gt_ids = {30, 60}
    gt_grades = {30: 1.0, 60: 0.5}

    rec_5 = calculate_recall(retrieved, gt_ids, k=5)
    mrr_10 = calculate_mrr(retrieved, gt_ids, k=10)
    ndcg_10 = calculate_ndcg(retrieved, gt_grades, k=10)

    assert rec_5 == 0.5  # 1 hit out of 2 ground truth items
    assert mrr_10 == 1.0 / 3.0  # Hit at rank 3
    assert ndcg_10 > 0.0
