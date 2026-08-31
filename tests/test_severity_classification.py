import os
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base,
    Repository,
    Issue,
    Label,
    SeverityPrediction,
    issue_labels,
)
from app.ml.severity_dataset import (
    format_severity_text,
    prepare_severity_dataset,
    SeverityExample,
)
from app.ml.severity_baseline import SeverityBaselineModel
from app.ml.severity_model import SeverityTransformerModel, get_device
from app.services.severity_classifier import SeverityClassifierService
from app.services.severity_evaluator import evaluate_severity_predictions


@pytest.fixture
def mock_db_session():
    """
    Creates an isolated in-memory SQLite engine and session for severity testing.
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
# Data & Label Filtering Tests (Phase 19: 1 - 5)
# ---------------------------------------------------------

def test_severity_labels_correctly_identified_and_mapped(mock_db_session):
    """1. Verify valid severity labels map to target IDs."""
    now = datetime.now(timezone.utc)
    repo = Repository(owner="org", name="app", full_name="org/app")
    mock_db_session.add(repo)
    mock_db_session.flush()

    lbl_high = Label(repository_id=repo.id, name="priority:high")
    lbl_bug = Label(repository_id=repo.id, name="bug")
    mock_db_session.add_all([lbl_high, lbl_bug])
    mock_db_session.flush()

    issue = Issue(
        github_issue_id=1, repository_id=repo.id, issue_number=101,
        title="Critical crash in production", body="Stack trace log", state="open",
        created_at=now, html_url="http://example.com/1"
    )
    issue.labels.append(lbl_high)
    issue.labels.append(lbl_bug)  # Non-severity label should be ignored
    mock_db_session.add(issue)
    mock_db_session.commit()

    split = prepare_severity_dataset(
        repository_id=repo.id,
        valid_severity_labels=["priority:low", "priority:high"],
        db_session=mock_db_session
    )

    all_examples = split.train_examples + split.val_examples + split.test_examples
    assert len(all_examples) == 1
    assert all_examples[0].target_label == "priority:high"
    assert all_examples[0].target_id == split.label_to_id["priority:high"]


def test_ambiguous_conflicting_severity_labels_excluded(mock_db_session):
    """2. Verify issues with multiple conflicting severity labels are excluded."""
    now = datetime.now(timezone.utc)
    repo = Repository(owner="org", name="app", full_name="org/app")
    mock_db_session.add(repo)
    mock_db_session.flush()

    lbl_high = Label(repository_id=repo.id, name="priority:high")
    lbl_low = Label(repository_id=repo.id, name="priority:low")
    mock_db_session.add_all([lbl_high, lbl_low])
    mock_db_session.flush()

    issue = Issue(
        github_issue_id=2, repository_id=repo.id, issue_number=102,
        title="Ambiguous issue", body="Has both high and low priority", state="open",
        created_at=now, html_url="http://example.com/2"
    )
    issue.labels.extend([lbl_high, lbl_low])
    mock_db_session.add(issue)
    mock_db_session.commit()

    split = prepare_severity_dataset(
        repository_id=repo.id,
        valid_severity_labels=["priority:low", "priority:high"],
        db_session=mock_db_session
    )

    assert len(split.train_examples) == 0
    assert split.ambiguous_excluded_count == 1


def test_unlabeled_issues_excluded(mock_db_session):
    """3. Verify issues without severity labels are excluded from dataset."""
    now = datetime.now(timezone.utc)
    repo = Repository(owner="org", name="app", full_name="org/app")
    mock_db_session.add(repo)
    mock_db_session.flush()

    issue = Issue(
        github_issue_id=3, repository_id=repo.id, issue_number=103,
        title="Unlabeled issue", body="No labels attached", state="open",
        created_at=now, html_url="http://example.com/3"
    )
    mock_db_session.add(issue)
    mock_db_session.commit()

    split = prepare_severity_dataset(
        repository_id=repo.id,
        valid_severity_labels=["priority:high"],
        db_session=mock_db_session
    )

    assert len(split.train_examples) == 0
    assert split.unlabeled_excluded_count == 1


def test_format_severity_text_no_ground_truth_leakage():
    """5. Verify ground-truth and internal IDs are excluded from model input text."""
    title = "Memory leak in background worker"
    body = "Memory usage grows continuously."
    text = format_severity_text(title, body)

    assert "Title:\nMemory leak in background worker" in text
    assert "Description:\nMemory usage grows continuously." in text
    assert "issue_id" not in text
    assert "duplicate_of" not in text
    assert "priority:" not in text


# ---------------------------------------------------------
# Temporal Split Tests (Phase 19: 6 - 8)
# ---------------------------------------------------------

def test_temporal_split_chronological_ordering(mock_db_session):
    """6, 7, 8. Verify strict chronological ordering across train, val, and test splits."""
    base_time = datetime.now(timezone.utc)
    repo = Repository(owner="org", name="app", full_name="org/app")
    mock_db_session.add(repo)
    mock_db_session.flush()

    lbl = Label(repository_id=repo.id, name="priority:high")
    mock_db_session.add(lbl)
    mock_db_session.flush()

    # Add 10 issues spaced by days
    for i in range(10):
        issue = Issue(
            github_issue_id=i+1, repository_id=repo.id, issue_number=i+1,
            title=f"Issue {i+1}", body=f"Body {i+1}", state="open",
            created_at=base_time + timedelta(days=i), html_url=f"http://example.com/{i+1}"
        )
        issue.labels.append(lbl)
        mock_db_session.add(issue)
    mock_db_session.commit()

    split = prepare_severity_dataset(
        repository_id=repo.id,
        valid_severity_labels=["priority:high"],
        train_ratio=0.70,
        val_ratio=0.15,
        db_session=mock_db_session
    )

    assert len(split.train_examples) == 7
    assert len(split.val_examples) == 1
    assert len(split.test_examples) == 2

    # Check temporal ordering
    max_train_date = max(ex.created_at for ex in split.train_examples)
    min_val_date = min(ex.created_at for ex in split.val_examples)
    max_val_date = max(ex.created_at for ex in split.val_examples)
    min_test_date = min(ex.created_at for ex in split.test_examples)

    assert max_train_date <= min_val_date
    assert max_val_date <= min_test_date

    # Check no overlap
    train_ids = {ex.issue_id for ex in split.train_examples}
    val_ids = {ex.issue_id for ex in split.val_examples}
    test_ids = {ex.issue_id for ex in split.test_examples}

    assert train_ids.isdisjoint(val_ids)
    assert val_ids.isdisjoint(test_ids)
    assert train_ids.isdisjoint(test_ids)


# ---------------------------------------------------------
# Inference & Database Separation Tests (Phase 19: 13 - 18)
# ---------------------------------------------------------

def test_inference_service_new_issue_without_database_id():
    """15 & 16. Verify new synthetic issue prediction without DB record and safe missing body handling."""
    service = SeverityClassifierService()
    res_1 = service.predict_severity(
        title="Application crash on startup",
        body="App exits immediately when launching executable."
    )

    assert res_1.predicted_label in ["low", "high"]
    assert 0.0 <= res_1.prediction_score <= 1.0
    assert res_1.query_issue_id is None

    # Test missing body handling
    res_2 = service.predict_severity(title="Blank body bug", body="")
    assert res_2.predicted_label in ["low", "high"]
    assert 0.0 <= res_2.prediction_score <= 1.0


def test_predict_and_persist_separate_from_ground_truth(mock_db_session):
    """17 & 18. Verify prediction persistence is stored in separate severity_predictions table."""
    now = datetime.now(timezone.utc)
    repo = Repository(owner="org", name="app", full_name="org/app")
    mock_db_session.add(repo)
    mock_db_session.flush()

    issue = Issue(
        github_issue_id=1, repository_id=repo.id, issue_number=50,
        title="Backend timeout", body="API request times out after 30s", state="open",
        created_at=now, html_url="http://example.com/50"
    )
    mock_db_session.add(issue)
    mock_db_session.commit()

    service = SeverityClassifierService()
    res = service.predict_and_persist(
        title=issue.title,
        body=issue.body,
        issue_id=issue.id,
        db_session=mock_db_session
    )

    # Verify separate severity_predictions table record
    predictions = mock_db_session.scalars(select(SeverityPrediction)).all()
    assert len(predictions) == 1
    assert predictions[0].issue_id == issue.id
    assert predictions[0].predicted_label == res.predicted_label
    assert predictions[0].prediction_score == res.prediction_score
