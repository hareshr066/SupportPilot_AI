import pytest
import numpy as np
import json
from pathlib import Path
from unittest.mock import MagicMock

from app.services.embedding_service import EmbeddingService
from app.services.root_cause_service import RootCauseService
from app.database.models import (
    Base,
    Repository,
    Issue,
    Label,
    IssueEmbedding,
    RootCauseCluster,
    RootCauseAssignment,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


from datetime import datetime, timezone

@pytest.fixture
def mock_embedding_service():
    mock_svc = MagicMock(spec=EmbeddingService)
    mock_svc.model_name = "BAAI/bge-small-en-v1.5"
    mock_svc.generate_issue_embedding.return_value = [0.1] * 384
    return mock_svc

@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()

    # Create dummy repository
    repo = Repository(owner="microsoft", name="vscode", full_name="microsoft/vscode")
    session.add(repo)
    session.flush()

    # Create dummy issues
    issues = []
    now = datetime.now(timezone.utc)
    for i in range(1, 21):
        is_closed = "closed" if i % 2 == 0 else "open"
        iss = Issue(
            github_issue_id=1000 + i,
            repository_id=repo.id,
            issue_number=i,
            title=f"Bug in module A issue #{i}" if i <= 10 else f"Crash in editor component issue #{i}",
            body=f"Detailed body text for issue number #{i} describing error.",
            state=is_closed,
            html_url=f"https://github.com/microsoft/vscode/issues/{i}",
            created_at=now,
            closed_at=now if is_closed == "closed" else None
        )
        session.add(iss)
        issues.append(iss)

    session.flush()

    # Add labels
    lbl_bug = Label(repository_id=repo.id, name="area-terminal")
    lbl_editor = Label(repository_id=repo.id, name="component-editor")
    session.add_all([lbl_bug, lbl_editor])
    session.flush()

    for idx, iss in enumerate(issues):
        if idx < 10:
            iss.labels.append(lbl_bug)
        else:
            iss.labels.append(lbl_editor)

    # Add embeddings (mock 384 dim vectors)
    np.random.seed(42)
    for iss in issues:
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


def test_closed_issue_corpus_selection(in_memory_db, mock_embedding_service):
    """1. Test closed-issue corpus selection."""
    service = RootCauseService(embedding_service=mock_embedding_service, db_session=in_memory_db)
    corpus = service.get_root_cause_corpus(repository_id=1, session=in_memory_db, state_filter="closed")

    assert len(corpus) == 10
    for item in corpus:
        assert item["issue_id"] is not None
        assert "embedding" in item
        assert len(item["embedding"]) == 384


def test_data_quality_filtering():
    """2. Test empty/invalid issue filtering."""
    service = RootCauseService()
    raw_corpus = [
        {"title": "Valid Issue", "body": "Valid body text describing bug", "embedding": [0.1] * 384},
        {"title": "", "body": "", "embedding": [0.1] * 384},  # Empty text
        {"title": "Short", "body": "123", "embedding": [0.1] * 384},  # Too short (<10 chars)
        {"title": "No Embedding", "body": "Valid text", "embedding": []},  # Missing embedding
    ]

    filtered, stats = service.filter_corpus(raw_corpus)
    assert len(filtered) == 1
    assert stats["total_closed"] == 4
    assert stats["eligible"] == 1
    assert stats["total_excluded"] == 3


def test_embedding_matrix_creation_and_nan_detection():
    """3 & 4. Test embedding matrix creation and NaN/Inf validation."""
    service = RootCauseService()
    corpus = [
        {"embedding": [1.0, 2.0, 3.0]},
        {"embedding": [4.0, 5.0, 6.0]}
    ]

    matrix = service.build_embedding_matrix(corpus)
    assert matrix.shape == (2, 3)

    # Test NaN detection
    invalid_corpus = [{"embedding": [1.0, float("nan"), 3.0]}]
    with pytest.raises(ValueError, match="NaN"):
        service.build_embedding_matrix(invalid_corpus)


def test_umap_and_hdbscan_pipeline():
    """5, 6, 7. Test UMAP reduction, HDBSCAN output, and noise handling."""
    service = RootCauseService()
    np.random.seed(42)
    matrix = np.random.randn(20, 384).astype(np.float32)

    reduced_10d = service.reduce_dimensions_umap(matrix, n_components=10)
    assert reduced_10d.shape == (20, 10)

    labels, probs, outliers = service.cluster_hdbscan(reduced_10d, min_cluster_size=3, min_samples=2)
    assert len(labels) == 20
    assert len(probs) == 20
    assert len(outliers) == 20


def test_representative_issue_selection():
    """10. Test representative issue selection."""
    service = RootCauseService()
    corpus = [
        {"issue_id": i, "issue_number": i, "title": f"Title {i}", "body": "Body text", "html_url": "url"}
        for i in range(10)
    ]
    labels = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    probs = np.ones(10, dtype=np.float32)
    matrix_10d = np.random.randn(10, 10).astype(np.float32)

    reps = service.select_representative_issues(corpus, labels, probs, matrix_10d, max_representatives=3)
    assert 0 in reps
    assert 1 in reps
    assert len(reps[0]) == 3


def test_component_label_extraction_and_purity_nmi():
    """11, 12, 13. Test component-label extraction, purity, and NMI calculation."""
    service = RootCauseService()
    corpus = [
        {"labels": ["area-terminal"]},
        {"labels": ["area-terminal"]},
        {"labels": ["component-editor"]},
        {"labels": ["component-editor"]},
    ]

    labels, indices = service.extract_component_labels(corpus)
    assert labels == ["area-terminal", "area-terminal", "component-editor", "component-editor"]
    assert len(indices) == 4

    cluster_labels = np.array([0, 0, 1, 1])
    metrics = service.evaluate_purity_and_nmi(cluster_labels, labels)

    assert metrics["weighted_purity"] == 1.0
    assert metrics["nmi"] == 1.0
    assert metrics["noise_count"] == 0


def test_invalid_llm_json_and_evidence_validation():
    """14 & 15. Test LLM fallback when API unavailable or evidence invalid."""
    service = RootCauseService()
    reps = {
        0: [
            {"issue_number": 101, "title": "Token refresh bug"},
            {"issue_number": 102, "title": "Auth failure"}
        ]
    }

    # Should not throw exception when OPENAI_API_KEY is not set
    labels = service.generate_llm_cluster_labels(reps)
    assert 0 in labels
    assert labels[0]["cluster_id"] == 0
    assert "label" in labels[0]
    assert set(labels[0]["evidence_issue_numbers"]).issubset({101, 102})


def test_persistence_and_multiple_runs(in_memory_db, mock_embedding_service):
    """8 & 9. Test database persistence and multiple distinct run_ids."""
    service = RootCauseService(embedding_service=mock_embedding_service, db_session=in_memory_db)
    corpus = service.get_root_cause_corpus(repository_id=1, session=in_memory_db)
    labels = np.array([0] * 5 + [1] * 5)
    probs = np.ones(10, dtype=np.float32)
    outliers = np.zeros(10, dtype=np.float32)
    summaries = {0: {"label": "C0"}, 1: {"label": "C1"}}

    run1 = service.persist_clustering_run(
        repository_id=1,
        run_id="run_test_001",
        corpus=corpus,
        labels=labels,
        probabilities=probs,
        outliers=outliers,
        cluster_summaries=summaries,
        umap_config={"n_components": 10},
        hdbscan_config={"min_cluster_size": 5},
        session=in_memory_db
    )

    run2 = service.persist_clustering_run(
        repository_id=1,
        run_id="run_test_002",
        corpus=corpus,
        labels=labels,
        probabilities=probs,
        outliers=outliers,
        cluster_summaries=summaries,
        umap_config={"n_components": 10},
        hdbscan_config={"min_cluster_size": 5},
        session=in_memory_db
    )

    assert run1["run_id"] != run2["run_id"]
    db_clusters = in_memory_db.scalars(select(RootCauseCluster)).all()
    assert len(db_clusters) == 4  # 2 clusters per run
