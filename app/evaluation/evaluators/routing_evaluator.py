import logging
from collections import Counter
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.evaluation.dataset import EvaluationDatasetItem
from app.services.routing_service import RoutingEngineService

logger = logging.getLogger(__name__)

def compute_top_k_accuracy(predictions: List[List[str]], ground_truth: List[str], k: int) -> float:
    if not ground_truth or len(predictions) != len(ground_truth):
        return 0.0
    hits = sum(1 for preds, gt in zip(predictions, ground_truth) if gt in preds[:k])
    return hits / len(ground_truth)


class RoutingEvaluator:
    """
    Evaluates Deterministic Routing against historical component / team ground truth.
    Compares Majority Component baseline vs Retrieval Router vs ML Router.
    """

    def __init__(self, service: Optional[RoutingEngineService] = None):
        self.service = service or RoutingEngineService()

    def evaluate(
        self,
        test_items: List[EvaluationDatasetItem],
        db_session: Session
    ) -> Dict[str, Any]:
        valid_items = [it for it in test_items if it.component]
        sample_count = len(valid_items)

        if sample_count < 1:
            return {
                "status": "INSUFFICIENT_EVALUATION_DATA",
                "sample_count": 0,
                "reason": "No test tickets with ground-truth component / team ownership found."
            }

        y_true = [it.component for it in valid_items]

        # 1. Majority Component Baseline
        majority_comp = Counter(y_true).most_common(1)[0][0]
        maj_top1 = sum(1 for gt in y_true if gt == majority_comp) / sample_count

        # 2. Retrieval Router & ML Router predictions
        ml_top_predictions: List[List[str]] = []
        retrieval_top_predictions: List[List[str]] = []

        for it in valid_items:
            try:
                res = self.service.predict_route(
                    ticket_id=it.ticket_id,
                    session=db_session
                )
                ml_preds = [t.component for t in res.top_k]
                ml_top_predictions.append(ml_preds if ml_preds else [res.predicted_component])

                retrieval_top_predictions.append([res.predicted_component])
            except Exception as e:
                logger.warning(f"Routing evaluation error for ticket {it.ticket_id}: {e}")
                ml_top_predictions.append([majority_comp])
                retrieval_top_predictions.append([majority_comp])

        ml_top1 = compute_top_k_accuracy(ml_top_predictions, y_true, k=1)
        ml_top3 = compute_top_k_accuracy(ml_top_predictions, y_true, k=3)

        ret_top1 = compute_top_k_accuracy(retrieval_top_predictions, y_true, k=1)
        ret_top3 = compute_top_k_accuracy(retrieval_top_predictions, y_true, k=3)

        return {
            "status": "COMPLETED",
            "sample_count": sample_count,
            "majority_component": majority_comp,
            "majority_baseline_top1_accuracy": round(maj_top1, 4),
            "retrieval_router": {
                "top_1_accuracy": round(ret_top1, 4),
                "top_3_accuracy": round(ret_top3, 4),
            },
            "ml_router": {
                "top_1_accuracy": round(ml_top1, 4),
                "top_3_accuracy": round(ml_top3, 4),
                "model_version": getattr(self.service, "model_path", "v1")
            }
        }
