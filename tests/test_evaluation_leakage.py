from datetime import datetime, timezone, timedelta
import pytest
from app.evaluation.leakage import LeakageValidator, TemporalLeakageError

def test_leakage_retrieval_future_ticket():
    t_now = datetime.now(timezone.utc)
    t_future = t_now + timedelta(days=5)

    retrieved = [
        {"ticket_id": 101, "created_at": t_now - timedelta(days=2)},
        {"ticket_id": 102, "created_at": t_future}  # Future ticket leakage
    ]

    with pytest.raises(TemporalLeakageError, match="Retrieval leakage"):
        LeakageValidator.validate_retrieval_corpus(t_now, retrieved, ticket_id=200)

def test_leakage_retrieval_self_retrieval():
    t_now = datetime.now(timezone.utc)

    retrieved = [
        {"ticket_id": 200, "created_at": t_now - timedelta(days=1)}  # Self retrieval
    ]

    with pytest.raises(TemporalLeakageError, match="retrieved itself"):
        LeakageValidator.validate_retrieval_corpus(t_now, retrieved, ticket_id=200)

def test_leakage_future_comment():
    t_now = datetime.now(timezone.utc)
    t_future_comment = t_now + timedelta(hours=3)

    with pytest.raises(TemporalLeakageError, match="Feature leakage"):
        LeakageValidator.validate_feature_timestamp(t_now, t_future_comment, "comment")

def test_leakage_future_label():
    t_now = datetime.now(timezone.utc)
    t_future_label = t_now + timedelta(days=1)

    with pytest.raises(TemporalLeakageError, match="Feature leakage"):
        LeakageValidator.validate_feature_timestamp(t_now, t_future_label, "label")

def test_leakage_future_assignee():
    t_now = datetime.now(timezone.utc)
    t_future_assignee = t_now + timedelta(days=2)

    with pytest.raises(TemporalLeakageError, match="Feature leakage"):
        LeakageValidator.validate_feature_timestamp(t_now, t_future_assignee, "assignee")

def test_leakage_future_pr():
    t_now = datetime.now(timezone.utc)
    t_future_pr = t_now + timedelta(days=4)

    with pytest.raises(TemporalLeakageError, match="Feature leakage"):
        LeakageValidator.validate_feature_timestamp(t_now, t_future_pr, "pull_request")

def test_leakage_threshold_tuning_on_test_set():
    with pytest.raises(TemporalLeakageError, match="Threshold selection must NOT use the held-out test set"):
        LeakageValidator.validate_threshold_tuning_split("test", "test")
