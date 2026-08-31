import logging
from collections import Counter
from typing import List, Dict, Any, Optional
from app.evaluation.dataset import EvaluationDatasetItem
from app.services.severity_classifier import SeverityClassifierService

logger = logging.getLogger(__name__)

def _normalize_severity_label(label: Optional[str]) -> Optional[str]:
    if not label:
        return None
    l = label.lower()
    if any(k in l for k in ["p0", "p1", "high", "critical"]):
        return "high"
    if any(k in l for k in ["p2", "p3", "low", "normal", "medium"]):
        return "low"
    return "low"

def compute_classification_metrics(y_true: List[str], y_pred: List[str]) -> Dict[str, Any]:
    if not y_true or len(y_true) != len(y_pred):
        return {
            "accuracy": 0.0,
            "macro_precision": 0.0,
            "macro_recall": 0.0,
            "macro_f1": 0.0,
            "weighted_f1": 0.0,
            "confusion_matrix": {}
        }

    classes = sorted(list(set(y_true + y_pred)))
    total = len(y_true)
    correct = sum(1 for gt, pr in zip(y_true, y_pred) if gt == pr)
    accuracy = correct / total if total > 0 else 0.0

    # Build confusion matrix
    cm: Dict[str, Dict[str, int]] = {c1: {c2: 0 for c2 in classes} for c1 in classes}
    for gt, pr in zip(y_true, y_pred):
        cm[gt][pr] += 1

    # Per-class metrics
    class_precisions = []
    class_recalls = []
    class_f1s = []
    class_counts = []

    for c in classes:
        tp = cm[c][c]
        fp = sum(cm[other][c] for other in classes if other != c)
        fn = sum(cm[c][other] for other in classes if other != c)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * (prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        class_precisions.append(prec)
        class_recalls.append(rec)
        class_f1s.append(f1)
        class_counts.append(sum(cm[c].values()))

    macro_precision = sum(class_precisions) / len(classes) if classes else 0.0
    macro_recall = sum(class_recalls) / len(classes) if classes else 0.0
    macro_f1 = sum(class_f1s) / len(classes) if classes else 0.0

    weighted_f1 = sum(f1 * count for f1, count in zip(class_f1s, class_counts)) / total if total > 0 else 0.0

    return {
        "accuracy": round(accuracy, 4),
        "macro_precision": round(macro_precision, 4),
        "macro_recall": round(macro_recall, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "confusion_matrix": cm
    }


class SeverityEvaluator:
    """
    Evaluates Severity Classification against historical ground-truth priority/severity labels.
    Compares ML Classifier vs Majority Class Baseline.
    """

    def __init__(self, service: Optional[SeverityClassifierService] = None):
        self.service = service or SeverityClassifierService()

    def evaluate(self, items: List[EvaluationDatasetItem]) -> Dict[str, Any]:
        # Filter items with valid ground-truth severity label
        valid_items = [it for it in items if _normalize_severity_label(it.severity_label) is not None]
        sample_count = len(valid_items)

        if sample_count < 3:
            return {
                "status": "INSUFFICIENT_EVALUATION_DATA",
                "sample_count": sample_count,
                "reason": "Fewer than 3 tickets with explicit severity ground-truth labels."
            }

        y_true = [_normalize_severity_label(it.severity_label) for it in valid_items]

        # 1. Majority Class Baseline
        majority_class = Counter(y_true).most_common(1)[0][0]
        y_pred_baseline = [majority_class] * sample_count
        baseline_metrics = compute_classification_metrics(y_true, y_pred_baseline)

        # 2. ML Classifier Prediction
        y_pred_ml = []
        for it in valid_items:
            res = self.service.predict_severity(it.title, it.body)
            y_pred_ml.append(_normalize_severity_label(res.predicted_label) or "low")

        ml_metrics = compute_classification_metrics(y_true, y_pred_ml)

        # Delta comparison
        f1_improvement = ml_metrics["weighted_f1"] - baseline_metrics["weighted_f1"]

        return {
            "status": "COMPLETED",
            "sample_count": sample_count,
            "majority_class": majority_class,
            "baseline": baseline_metrics,
            "ml_classifier": ml_metrics,
            "weighted_f1_improvement": round(f1_improvement, 4),
            "model_version": self.service.model.model_name
        }
