import pytest
import numpy as np
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base,
    Repository,
    User,
    Label,
    Issue,
    IssueEmbedding,
    issue_labels,
)
from app.services.embedding_service import (
    EmbeddingService,
    build_issue_embedding_text,
)
from app.services.duplicate_detector import DuplicateDetector
from app.services.evaluation import (
    DuplicateEvaluationService,
    calculate_retrieval_recalls,
    calculate_classification_metrics,
)


@pytest.fixture
def mock_db_session():
    """
    Creates an isolated in-memory SQLite engine and session for duplicate detection testing.
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------
# Test Cases: Embedding Generation & Leakage Protection
# ---------------------------------------------------------

def test_build_issue_embedding_text_determinism():
    """1. Verify same issue produces deterministic embedding input text."""
    issue_dict = {
        "title": "Fix terminal crash on Windows",
        "body": "Terminal exits abruptly when opening bash prompt.",
        "labels": [{"name": "bug"}, {"name": "terminal"}]
    }
    text_1 = build_issue_embedding_text(issue_dict)
    text_2 = build_issue_embedding_text(issue_dict)

    assert text_1 == text_2
    assert "Title:\nFix terminal crash on Windows" in text_1
    assert "Description:\nTerminal exits abruptly when opening bash prompt." in text_1
    assert "Labels:\nbug, terminal" in text_1


def test_build_issue_embedding_text_no_ground_truth_leakage():
    """3. Verify ground-truth duplicate fields are NOT included in embedding text."""
    issue_dict = {
        "title": "Fix terminal crash",
        "body": "Terminal exits abruptly.",
        "duplicate_of_issue_number": 999,
        "duplicate_detected": True
    }
    text = build_issue_embedding_text(issue_dict)

    assert "999" not in text
    assert "duplicate_of" not in text
    assert "duplicate_detected" not in text


def test_embedding_dimension_matches_model():
    """2. Verify embedding dimension matches configured model."""
    service = EmbeddingService()
    text = "Title:\nTest issue title"
    vector = service.generate_text_embedding(text)

    assert len(vector) == service.get_embedding_dimension()
    assert isinstance(vector, list)
    assert isinstance(vector[0], float)


# ---------------------------------------------------------
# Test Cases: Candidate Retrieval & Filtering
# ---------------------------------------------------------

def test_query_issue_excluded_from_own_candidates(mock_db_session):
    """4 & 6. Verify query issue is excluded from candidates and Top-K is respected."""
    now = datetime.now(timezone.utc)
    repo = Repository(owner="org", name="app", full_name="org/app")
    mock_db_session.add(repo)
    mock_db_session.flush()

    # Add issues
    issue_1 = Issue(
        github_issue_id=1, repository_id=repo.id, issue_number=1,
        title="Terminal crash", body="Crash log", state="open",
        created_at=now - timedelta(days=2), html_url="http://example.com/1"
    )
    issue_2 = Issue(
        github_issue_id=2, repository_id=repo.id, issue_number=2,
        title="Terminal crash variant", body="Crash log variant", state="open",
        created_at=now - timedelta(days=1), html_url="http://example.com/2"
    )
    mock_db_session.add_all([issue_1, issue_2])
    mock_db_session.flush()

    # Add mock embeddings (dimension 384)
    dummy_vector = [0.1] * 384
    emb_1 = IssueEmbedding(issue_id=issue_1.id, model_name="BAAI/bge-small-en-v1.5", embedding=dummy_vector)
    emb_2 = IssueEmbedding(issue_id=issue_2.id, model_name="BAAI/bge-small-en-v1.5", embedding=dummy_vector)
    mock_db_session.add_all([emb_1, emb_2])
    mock_db_session.commit()

    detector = DuplicateDetector()
    candidates = detector.find_similar_issues(
        issue_id=issue_1.id,
        repository_id=repo.id,
        top_k=10,
        exclude_self=True,
        db_session=mock_db_session
    )

    candidate_ids = [c.issue_id for c in candidates]
    assert issue_1.id not in candidate_ids
    assert issue_2.id in candidate_ids


def test_repository_scoping_filter(mock_db_session):
    """5. Verify candidate retrieval is restricted to the specified repository."""
    now = datetime.now(timezone.utc)
    repo_a = Repository(owner="org", name="app_a", full_name="org/app_a")
    repo_b = Repository(owner="org", name="app_b", full_name="org/app_b")
    mock_db_session.add_all([repo_a, repo_b])
    mock_db_session.flush()

    issue_a = Issue(
        github_issue_id=1, repository_id=repo_a.id, issue_number=1,
        title="Crash in App A", body="Crash details", state="open",
        created_at=now, html_url="http://example.com/1"
    )
    issue_b = Issue(
        github_issue_id=2, repository_id=repo_b.id, issue_number=1,
        title="Crash in App B", body="Crash details", state="open",
        created_at=now, html_url="http://example.com/2"
    )
    mock_db_session.add_all([issue_a, issue_b])
    mock_db_session.flush()

    dummy_vector = [0.2] * 384
    mock_db_session.add_all([
        IssueEmbedding(issue_id=issue_a.id, model_name="BAAI/bge-small-en-v1.5", embedding=dummy_vector),
        IssueEmbedding(issue_id=issue_b.id, model_name="BAAI/bge-small-en-v1.5", embedding=dummy_vector),
    ])
    mock_db_session.commit()

    detector = DuplicateDetector()
    candidates = detector.find_similar_issues_for_text(
        title="Crash in App A",
        body="Crash details",
        repository_id=repo_a.id,
        top_k=10,
        db_session=mock_db_session
    )

    assert len(candidates) == 1
    assert candidates[0].issue_id == issue_a.id


# ---------------------------------------------------------
# Test Cases: Evaluation & Metrics Calculation
# ---------------------------------------------------------

def test_recall_at_k_calculation():
    """14. Verify Recall@K calculation functions."""
    retrieved = [10, 20, 30, 40, 50]
    
    rec_hit_1 = calculate_retrieval_recalls(retrieved, 10)
    assert rec_hit_1["at_1"] is True
    assert rec_hit_1["at_5"] is True

    rec_hit_5 = calculate_retrieval_recalls(retrieved, 50)
    assert rec_hit_5["at_1"] is False
    assert rec_hit_5["at_5"] is True

    rec_miss = calculate_retrieval_recalls(retrieved, 999)
    assert rec_miss["at_20"] is False


def test_classification_metrics_calculation():
    """13. Verify Precision, Recall, and F1 calculations."""
    # TP=8, FP=2, FN=2
    p, r, f1 = calculate_classification_metrics(tp=8, fp=2, fn=2)
    assert p == 0.8  # 8 / (8 + 2)
    assert r == 0.8  # 8 / (8 + 2)
    assert pytest.approx(f1, 0.001) == 0.8
