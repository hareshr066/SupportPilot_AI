import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import Issue, Repository
from app.services.duplicate_detector import DuplicateDetector, CandidateIssue

logger = logging.getLogger(__name__)


class EvaluationMetrics(BaseModel):
    total_eval_queries: int = 0
    ground_truth_pairs_found: int = 0
    recall_at_1: float = 0.0
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    recall_at_20: float = 0.0
    selected_threshold: float = 0.5
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    threshold_grid_results: List[Dict[str, float]] = []


def calculate_retrieval_recalls(retrieved_issue_numbers: List[int], target_issue_number: int) -> Dict[str, bool]:
    """
    Checks if target_issue_number appears within Recall@K cutoffs.
    """
    return {
        "at_1": target_issue_number in retrieved_issue_numbers[:1],
        "at_5": target_issue_number in retrieved_issue_numbers[:5],
        "at_10": target_issue_number in retrieved_issue_numbers[:10],
        "at_20": target_issue_number in retrieved_issue_numbers[:20],
    }


def calculate_classification_metrics(
    tp: int, fp: int, fn: int
) -> Tuple[float, float, float]:
    """
    Calculates Precision, Recall, and F1 score safely.
    """
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


class DuplicateEvaluationService:
    """
    Service responsible for constructing temporal ground-truth evaluation datasets,
    evaluating Stage 1 Retrieval (Recall@K), tuning Cross-Encoder thresholds, and
    computing final classification metrics (Precision, Recall, F1).
    """

    def __init__(self, detector: Optional[DuplicateDetector] = None):
        self.detector = detector or DuplicateDetector()

    def evaluate_repository(
        self,
        repository_id: int,
        val_test_split_ratio: float = 0.5,
        threshold_grid: Optional[List[float]] = None,
        db_session: Optional[Session] = None
    ) -> EvaluationMetrics:
        """
        Runs evaluation on historical duplicate ground truth for repository_id.
        """
        grid = threshold_grid or [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]

        def _eval_with_session(session: Session) -> EvaluationMetrics:
            # Query all issues with explicit ground-truth duplicate references
            query_issues = session.scalars(
                select(Issue).where(
                    Issue.repository_id == repository_id,
                    Issue.duplicate_of_issue_number.isnot(None)
                ).order_by(Issue.created_at.asc())
            ).all()

            if not query_issues:
                logger.warning(f"No ground-truth duplicate issues found for repository_id={repository_id}.")
                return EvaluationMetrics(total_eval_queries=0, ground_truth_pairs_found=0)

            # Build ground-truth evaluation pairs
            eval_pairs: List[Dict[str, Any]] = []
            for q_issue in query_issues:
                target_num = q_issue.duplicate_of_issue_number
                target_issue = session.scalar(
                    select(Issue).where(
                        Issue.repository_id == repository_id,
                        Issue.issue_number == target_num
                    )
                )
                if target_issue:
                    eval_pairs.append({
                        "query": q_issue,
                        "target_number": target_num,
                        "target_issue_id": target_issue.id
                    })

            total_pairs = len(eval_pairs)
            if total_pairs == 0:
                logger.warning("Found duplicate numbers, but referenced target issues do not exist in database.")
                return EvaluationMetrics(total_eval_queries=len(query_issues), ground_truth_pairs_found=0)

            logger.info(f"Evaluation dataset contains {total_pairs} ground-truth duplicate pairs.")

            # Temporal Train/Val vs Test split
            split_idx = int(total_pairs * val_test_split_ratio)
            val_pairs = eval_pairs[:split_idx] if split_idx > 0 else eval_pairs
            test_pairs = eval_pairs[split_idx:] if split_idx < total_pairs else eval_pairs

            # 1. Evaluate Stage 1 Retrieval (Recall@K) across all pairs
            r1_hits = r5_hits = r10_hits = r20_hits = 0

            for pair in eval_pairs:
                q_issue = pair["query"]
                target_num = pair["target_number"]

                candidates = self.detector.find_similar_issues(
                    issue_id=q_issue.id,
                    repository_id=repository_id,
                    top_k=20,
                    exclude_self=True,
                    filter_before_created_at=q_issue.created_at,
                    db_session=session
                )

                retrieved_nums = [c.issue_number for c in candidates]
                rec = calculate_retrieval_recalls(retrieved_nums, target_num)

                if rec["at_1"]: r1_hits += 1
                if rec["at_5"]: r5_hits += 1
                if rec["at_10"]: r10_hits += 1
                if rec["at_20"]: r20_hits += 1

            recall_at_1 = r1_hits / total_pairs
            recall_at_5 = r5_hits / total_pairs
            recall_at_10 = r10_hits / total_pairs
            recall_at_20 = r20_hits / total_pairs

            # 2. Grid Search Cross-Encoder Threshold on Validation Set
            grid_results = []
            best_thresh = 0.5
            best_val_f1 = -1.0

            for thresh in grid:
                val_tp = val_fp = val_fn = 0
                for pair in val_pairs:
                    q_issue = pair["query"]
                    target_num = pair["target_number"]

                    res = self.detector.detect_duplicate(
                        title=q_issue.title,
                        body=q_issue.body,
                        repository_id=repository_id,
                        query_issue_id=q_issue.id,
                        query_issue_number=q_issue.issue_number,
                        filter_before_created_at=q_issue.created_at,
                        custom_threshold=thresh,
                        db_session=session
                    )

                    if res.is_duplicate:
                        if res.matched_issue_number == target_num:
                            val_tp += 1
                        else:
                            val_fp += 1
                    else:
                        val_fn += 1

                p, r, f1 = calculate_classification_metrics(val_tp, val_fp, val_fn)
                grid_results.append({
                    "threshold": thresh,
                    "precision": round(p, 4),
                    "recall": round(r, 4),
                    "f1": round(f1, 4)
                })

                if f1 > best_val_f1:
                    best_val_f1 = f1
                    best_thresh = thresh

            logger.info(f"Selected optimal validation threshold: {best_thresh} (Val F1={best_val_f1:.4f})")

            # 3. Final Evaluation on Test Set using Selected Threshold
            test_tp = test_fp = test_fn = 0
            for pair in test_pairs:
                q_issue = pair["query"]
                target_num = pair["target_number"]

                res = self.detector.detect_duplicate(
                    title=q_issue.title,
                    body=q_issue.body,
                    repository_id=repository_id,
                    query_issue_id=q_issue.id,
                    query_issue_number=q_issue.issue_number,
                    filter_before_created_at=q_issue.created_at,
                    custom_threshold=best_thresh,
                    db_session=session
                )

                if res.is_duplicate:
                    if res.matched_issue_number == target_num:
                        test_tp += 1
                    else:
                        test_fp += 1
                else:
                    test_fn += 1

            test_p, test_r, test_f1 = calculate_classification_metrics(test_tp, test_fp, test_fn)

            return EvaluationMetrics(
                total_eval_queries=len(query_issues),
                ground_truth_pairs_found=total_pairs,
                recall_at_1=round(recall_at_1, 4),
                recall_at_5=round(recall_at_5, 4),
                recall_at_10=round(recall_at_10, 4),
                recall_at_20=round(recall_at_20, 4),
                selected_threshold=best_thresh,
                precision=round(test_p, 4),
                recall=round(test_r, 4),
                f1_score=round(test_f1, 4),
                true_positives=test_tp,
                false_positives=test_fp,
                false_negatives=test_fn,
                threshold_grid_results=grid_results
            )

        if db_session:
            return _eval_with_session(db_session)
        else:
            with get_db() as session:
                return _eval_with_session(session)
