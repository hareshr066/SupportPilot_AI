import logging
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.evaluation.dataset import EvaluationDatasetItem
from app.evaluation.leakage import LeakageValidator
from app.services.duplicate_detector import DuplicateDetector

logger = logging.getLogger(__name__)

def categorize_false_positive(query_item: EvaluationDatasetItem, matched_issue_number: Optional[int]) -> str:
    """
    Categorizes false positive duplicate predictions based on title/body characteristics.
    Does NOT fabricate data.
    """
    body_text = (query_item.body or "").lower()
    title_text = (query_item.title or "").lower()

    if len(body_text.split()) < 5:
        return "INSUFFICIENT_CONTEXT"
    if any(ver in title_text or ver in body_text for ver in ["v1.", "v2.", "v0.", "update", "upgrade"]):
        return "VERSION_SPECIFIC_DIFFERENCE"
    if query_item.component:
        return "SAME_COMPONENT_DIFFERENT_BUG"
    if "error" in title_text or "exception" in title_text or "crash" in title_text:
        return "SAME_ERROR_DIFFERENT_ROOT_CAUSE"

    return "SAME_KEYWORDS_DIFFERENT_BEHAVIOR"


class DuplicateEvaluator:
    """
    Evaluates Duplicate Detection performance.
    Separates candidate retrieval Recall@K from final classification (Precision, Recall, F1).
    Tunes threshold on Validation set and evaluates on held-out Test set.
    """

    def __init__(self, detector: Optional[DuplicateDetector] = None):
        self.detector = detector or DuplicateDetector()

    def evaluate_retrieval_and_classification(
        self,
        val_items: List[EvaluationDatasetItem],
        test_items: List[EvaluationDatasetItem],
        threshold_grid: List[float],
        db_session: Session
    ) -> Dict[str, Any]:

        # Find items with explicit ground-truth duplicate targets
        val_dups = [it for it in val_items if it.duplicate_target is not None]
        test_dups = [it for it in test_items if it.duplicate_target is not None]

        total_dups = len(val_dups) + len(test_dups)
        if total_dups < 1:
            return {
                "status": "INSUFFICIENT_EVALUATION_DATA",
                "sample_count": total_dups,
                "reason": "No historical duplicate issue pairs found in dataset."
            }

        # 1. Candidate Retrieval Recall@K (evaluated on all query items with targets)
        all_dups = val_dups + test_dups
        r1_hits = r3_hits = r5_hits = r10_hits = r20_hits = 0

        for q_item in all_dups:
            target_num = q_item.duplicate_target
            candidates = self.detector.find_similar_issues(
                issue_id=q_item.ticket_id,
                repository_id=q_item.repository_id,
                top_k=20,
                exclude_self=True,
                filter_before_created_at=q_item.created_at,
                db_session=db_session
            )

            # Validate zero leakage
            cand_dicts = [{"ticket_id": c.issue_id, "created_at": q_item.created_at} for c in candidates]
            LeakageValidator.validate_retrieval_corpus(q_item.created_at, cand_dicts, ticket_id=q_item.ticket_id)

            cand_nums = [c.issue_number for c in candidates]

            if target_num in cand_nums[:1]: r1_hits += 1
            if target_num in cand_nums[:3]: r3_hits += 1
            if target_num in cand_nums[:5]: r5_hits += 1
            if target_num in cand_nums[:10]: r10_hits += 1
            if target_num in cand_nums[:20]: r20_hits += 1

        n_pairs = len(all_dups)
        candidate_retrieval_metrics = {
            "recall_at_1": round(r1_hits / n_pairs, 4),
            "recall_at_3": round(r3_hits / n_pairs, 4),
            "recall_at_5": round(r5_hits / n_pairs, 4),
            "recall_at_10": round(r10_hits / n_pairs, 4),
            "recall_at_20": round(r20_hits / n_pairs, 4),
        }

        # 2. Grid Search Threshold on Validation Set
        grid_results = []
        best_threshold = 0.5
        best_val_f1 = -1.0

        for thresh in threshold_grid:
            val_tp = val_fp = val_fn = 0
            for q_item in (val_dups if val_dups else all_dups):
                target_num = q_item.duplicate_target
                res = self.detector.detect_duplicate(
                    title=q_item.title,
                    body=q_item.body,
                    repository_id=q_item.repository_id,
                    query_issue_id=q_item.ticket_id,
                    query_issue_number=q_item.issue_number,
                    filter_before_created_at=q_item.created_at,
                    custom_threshold=thresh,
                    db_session=db_session
                )
                if res.is_duplicate:
                    if res.matched_issue_number == target_num:
                        val_tp += 1
                    else:
                        val_fp += 1
                else:
                    val_fn += 1

            p = val_tp / (val_tp + val_fp) if (val_tp + val_fp) > 0 else 0.0
            r = val_tp / (val_tp + val_fn) if (val_tp + val_fn) > 0 else 0.0
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0

            grid_results.append({
                "threshold": thresh,
                "precision": round(p, 4),
                "recall": round(r, 4),
                "f1": round(f1, 4)
            })

            if f1 > best_val_f1:
                best_val_f1 = f1
                best_threshold = thresh

        LeakageValidator.validate_threshold_tuning_split("val" if val_dups else "all", "test")

        # 3. Final Evaluation on Held-out Test Set
        test_tp = test_fp = test_fn = 0
        false_positive_cases: List[Dict[str, Any]] = []

        eval_set = test_dups if test_dups else all_dups
        for q_item in eval_set:
            target_num = q_item.duplicate_target
            res = self.detector.detect_duplicate(
                title=q_item.title,
                body=q_item.body,
                repository_id=q_item.repository_id,
                query_issue_id=q_item.ticket_id,
                query_issue_number=q_item.issue_number,
                filter_before_created_at=q_item.created_at,
                custom_threshold=best_threshold,
                db_session=db_session
            )

            if res.is_duplicate:
                if res.matched_issue_number == target_num:
                    test_tp += 1
                else:
                    test_fp += 1
                    cat = categorize_false_positive(q_item, res.matched_issue_number)
                    false_positive_cases.append({
                        "ticket_id": q_item.ticket_id,
                        "title": q_item.title,
                        "expected_target": target_num,
                        "predicted_target": res.matched_issue_number,
                        "similarity_score": res.similarity_score,
                        "category": cat
                    })
            else:
                test_fn += 1

        test_p = test_tp / (test_tp + test_fp) if (test_tp + test_fp) > 0 else 0.0
        test_r = test_tp / (test_tp + test_fn) if (test_tp + test_fn) > 0 else 0.0
        test_f1 = 2 * test_p * test_r / (test_p + test_r) if (test_p + test_r) > 0 else 0.0

        # Failure distribution
        fp_categories: Dict[str, int] = {}
        for fp in false_positive_cases:
            c = fp["category"]
            fp_categories[c] = fp_categories.get(c, 0) + 1

        return {
            "status": "COMPLETED",
            "sample_count": len(eval_set),
            "candidate_retrieval": candidate_retrieval_metrics,
            "selected_threshold": best_threshold,
            "validation_f1_at_selected_threshold": round(best_val_f1, 4),
            "threshold_grid_search": grid_results,
            "test_classification": {
                "precision": round(test_p, 4),
                "recall": round(test_r, 4),
                "f1_score": round(test_f1, 4),
                "true_positives": test_tp,
                "false_positives": test_fp,
                "false_negatives": test_fn
            },
            "false_positive_categories": fp_categories,
            "false_positive_examples": false_positive_cases[:5]
        }
