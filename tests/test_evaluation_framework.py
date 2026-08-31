from datetime import datetime, timezone, timedelta
import pytest
from app.evaluation.config import EvaluationConfig
from app.evaluation.dataset import EvaluationDatasetItem, EvaluationDatasetBuilder
from app.evaluation.evaluators.severity_evaluator import SeverityEvaluator, compute_classification_metrics
from app.evaluation.evaluators.duplicate_evaluator import DuplicateEvaluator, categorize_false_positive
from app.evaluation.evaluators.root_cause_evaluator import RootCauseEvaluator, calculate_cluster_purity
from app.evaluation.evaluators.retrieval_evaluator import RetrievalEvaluator, calculate_mrr
from app.evaluation.evaluators.resolution_evaluator import ResolutionEvaluator, compute_cosine_similarity
from app.evaluation.evaluators.calibration_evaluator import CalibrationEvaluator, compute_brier_score, compute_ece
from app.evaluation.evaluators.routing_evaluator import RoutingEvaluator, compute_top_k_accuracy
from app.evaluation.evaluators.failure_analyzer import FailureAnalyzer
from app.evaluation.evaluators.e2e_evaluator import EndToEndEvaluator
from app.evaluation.runner import MasterEvaluationRunner

def test_dataset_item_creation():
    now = datetime.now(timezone.utc)
    item = EvaluationDatasetItem(
        ticket_id=1,
        repository_id=10,
        issue_number=42,
        title="Test issue title",
        body="Test issue body",
        labels=["severity:high", "area:ui"],
        state="closed",
        assignees=["dev1"],
        duplicate_target=None,
        component="ui",
        resolution_ground_truth="Fixed by updating CSS",
        linked_pr=12,
        closing_comment="Fixed by updating CSS",
        created_at=now,
        closed_at=now + timedelta(hours=1),
        severity_label="severity:high"
    )

    d = item.to_dict()
    assert d["ticket_id"] == 1
    assert d["severity_label"] == "severity:high"
    assert d["component"] == "ui"

def test_temporal_split():
    now = datetime.now(timezone.utc)
    items = [
        EvaluationDatasetItem(
            ticket_id=i, repository_id=1, issue_number=i, title=f"Issue {i}", body="",
            labels=[], state="open", assignees=[], duplicate_target=None, component=None,
            resolution_ground_truth=None, linked_pr=None, closing_comment=None,
            created_at=now + timedelta(days=i), closed_at=None
        )
        for i in range(10)
    ]

    builder = EvaluationDatasetBuilder(EvaluationConfig())
    train, val, test, info = builder.create_temporal_split(items)

    assert len(train) == 6
    assert len(val) == 2
    assert len(test) == 2
    assert train[0].created_at < val[0].created_at < test[0].created_at

def test_severity_classification_metrics():
    y_true = ["high", "low", "high", "low"]
    y_pred = ["high", "low", "low", "low"]

    metrics = compute_classification_metrics(y_true, y_pred)
    assert metrics["accuracy"] == 0.75
    assert "confusion_matrix" in metrics

def test_mrr_calculation():
    assert calculate_mrr([10, 20, 30], 10) == 1.0
    assert calculate_mrr([10, 20, 30], 20) == 0.5
    assert calculate_mrr([10, 20, 30], 30) == (1.0 / 3.0)
    assert calculate_mrr([10, 20, 30], 99) == 0.0

def test_cosine_similarity():
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]

    assert compute_cosine_similarity(v1, v2) == 1.0
    assert compute_cosine_similarity(v1, v3) == 0.0

def test_calibration_brier_and_ece():
    confs = [0.9, 0.8, 0.2, 0.1]
    outcomes = [1, 1, 0, 0]

    brier = compute_brier_score(confs, outcomes)
    assert brier < 0.1

    ece, bins = compute_ece(confs, outcomes)
    assert ece >= 0.0
    assert len(bins) > 0

def test_small_dataset_handling():
    now = datetime.now(timezone.utc)
    single_item = [
        EvaluationDatasetItem(
            ticket_id=1, repository_id=1, issue_number=1, title="Tiny", body="",
            labels=[], state="open", assignees=[], duplicate_target=None, component=None,
            resolution_ground_truth=None, linked_pr=None, closing_comment=None,
            created_at=now, closed_at=None
        )
    ]

    evaluator = SeverityEvaluator()
    res = evaluator.evaluate(single_item)
    assert res["status"] == "INSUFFICIENT_EVALUATION_DATA"
    assert res["sample_count"] == 0
