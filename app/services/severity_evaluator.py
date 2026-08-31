import os
import json
import logging
from typing import List, Dict, Tuple, Any, Optional
import numpy as np
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix

from app.ml.severity_dataset import SeverityExample

logger = logging.getLogger(__name__)


class SeverityEvaluationReport(BaseModel := type('BaseModel', (), {})):
    pass


def evaluate_severity_predictions(
    y_true: List[int],
    y_pred: List[int],
    y_scores: List[float],
    examples: List[SeverityExample],
    id_to_label: Dict[int, str]
) -> Dict[str, Any]:
    """
    Computes comprehensive evaluation metrics:
      - Accuracy
      - Macro Precision, Macro Recall, Macro F1 (Primary metric for class imbalance)
      - Weighted F1
      - Per-class Precision, Recall, F1, Support
      - Confusion Matrix
      - Error Analysis (grouped misclassifications)
    """
    if not y_true or not y_pred:
        return {
            "total_examples": 0,
            "accuracy": 0.0,
            "macro_precision": 0.0,
            "macro_recall": 0.0,
            "macro_f1": 0.0,
            "weighted_f1": 0.0,
            "per_class": {},
            "confusion_matrix": [],
            "error_analysis": []
        }

    acc = float(accuracy_score(y_true, y_pred))
    p_macro, r_macro, f1_macro, _ = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0
    )
    _, _, f1_weighted, _ = precision_recall_fscore_support(
        y_true, y_pred, average="weighted", zero_division=0
    )

    class_ids = sorted(list(id_to_label.keys()))
    p_class, r_class, f1_class, support_class = precision_recall_fscore_support(
        y_true, y_pred, labels=class_ids, average=None, zero_division=0
    )

    per_class_metrics = {}
    for cid, p, r, f1, sup in zip(class_ids, p_class, r_class, f1_class, support_class):
        lbl = id_to_label.get(cid, str(cid))
        per_class_metrics[lbl] = {
            "precision": round(float(p), 4),
            "recall": round(float(r), 4),
            "f1": round(float(f1), 4),
            "support": int(sup)
        }

    cm = confusion_matrix(y_true, y_pred, labels=class_ids).tolist()

    # Error analysis: collect misclassified examples
    error_list = []
    for ex, true_id, pred_id, score in zip(examples, y_true, y_pred, y_scores):
        if true_id != pred_id:
            error_list.append({
                "issue_id": ex.issue_id,
                "title": ex.title,
                "true_label": id_to_label.get(true_id, str(true_id)),
                "predicted_label": id_to_label.get(pred_id, str(pred_id)),
                "prediction_score": round(float(score), 4)
            })

    return {
        "total_examples": len(y_true),
        "accuracy": round(acc, 4),
        "macro_precision": round(float(p_macro), 4),
        "macro_recall": round(float(r_macro), 4),
        "macro_f1": round(float(f1_macro), 4),
        "weighted_f1": round(float(f1_weighted), 4),
        "per_class": per_class_metrics,
        "confusion_matrix": cm,
        "class_labels": [id_to_label.get(cid, str(cid)) for cid in class_ids],
        "error_analysis": error_list
    }


def save_evaluation_report(report: Dict[str, Any], output_path: str):
    """Saves structured evaluation report and confusion matrix to JSON file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Evaluation report saved to '{output_path}'.")
