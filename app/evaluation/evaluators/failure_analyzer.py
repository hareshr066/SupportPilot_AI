import logging
from typing import List, Dict, Any, Optional

from app.evaluation.dataset import EvaluationDatasetItem

logger = logging.getLogger(__name__)

class FailureAnalyzer:
    """
    Automated failure analysis and error budget breakdown.
    Categorizes stage failures, analyzes high-confidence errors vs missed automation opportunities,
    and isolates retrieval errors from generation errors.
    """

    def analyze_failures(
        self,
        test_items: List[EvaluationDatasetItem],
        stage_eval_results: Dict[str, Any]
    ) -> Dict[str, Any]:

        failures: List[Dict[str, Any]] = []
        stage_counts: Dict[str, int] = {
            "SEVERITY": 0,
            "DUPLICATE": 0,
            "RETRIEVAL": 0,
            "RESOLUTION": 0,
            "FAITHFULNESS": 0,
            "CALIBRATION": 0,
            "ROUTING": 0
        }

        # 1. Collect Duplicate FPs/FNs
        dup_res = stage_eval_results.get("duplicate", {})
        if dup_res.get("status") == "COMPLETED":
            for fp in dup_res.get("false_positive_examples", []):
                failures.append({
                    "ticket_id": fp.get("ticket_id"),
                    "failed_stage": "DUPLICATE",
                    "failure_category": "DUPLICATE_FALSE_POSITIVE",
                    "reason_code": fp.get("category", "DUPLICATE_FALSE_POSITIVE"),
                    "predicted_result": {"matched_issue_number": fp.get("predicted_target")},
                    "ground_truth": {"expected_target": fp.get("expected_target")},
                    "evidence_json": {"similarity_score": fp.get("similarity_score")}
                })
                stage_counts["DUPLICATE"] += 1

        # 2. Collect Retrieval Misses
        ret_res = stage_eval_results.get("retrieval", {})
        if ret_res.get("status") == "COMPLETED":
            ret_metrics = ret_res.get("hybrid_retrieval", {})
            mrr = ret_metrics.get("mrr", 0.0)
            if mrr < 0.5:
                failures.append({
                    "ticket_id": None,
                    "failed_stage": "RETRIEVAL",
                    "failure_category": "RETRIEVAL_MISS",
                    "reason_code": "LOW_RETRIVAL_MRR",
                    "predicted_result": {"mrr": mrr},
                    "ground_truth": {"expected_mrr": 1.0},
                    "evidence_json": ret_metrics
                })
                stage_counts["RETRIEVAL"] += 1

        # 3. Collect Resolution / Faithfulness Failures
        res_eval = stage_eval_results.get("resolution", {})
        if res_eval.get("status") == "COMPLETED":
            if res_eval.get("unsupported_claims_count", 0) > 0:
                failures.append({
                    "ticket_id": None,
                    "failed_stage": "FAITHFULNESS",
                    "failure_category": "UNSUPPORTED_CLAIM",
                    "reason_code": "FAITHFULNESS_UNSUPPORTED_CLAIMS",
                    "predicted_result": {"unsupported_claims": res_eval.get("unsupported_claims_count")},
                    "ground_truth": {"expected_unsupported_claims": 0},
                    "evidence_json": {"faithfulness_rate": res_eval.get("faithfulness_rate")}
                })
                stage_counts["FAITHFULNESS"] += 1

            if res_eval.get("contradicted_claims_count", 0) > 0:
                failures.append({
                    "ticket_id": None,
                    "failed_stage": "FAITHFULNESS",
                    "failure_category": "CONTRADICTED_CLAIM",
                    "reason_code": "FAITHFULNESS_CONTRADICTED_CLAIMS",
                    "predicted_result": {"contradicted_claims": res_eval.get("contradicted_claims_count")},
                    "ground_truth": {"expected_contradicted_claims": 0},
                    "evidence_json": {"faithfulness_rate": res_eval.get("faithfulness_rate")}
                })
                stage_counts["FAITHFULNESS"] += 1

        total_failures = len(failures)
        stage_percentages = {
            st: round((cnt / total_failures * 100), 1) if total_failures > 0 else 0.0
            for st, cnt in stage_counts.items()
        }

        # Category frequency ranking
        cat_counts: Dict[str, int] = {}
        for f in failures:
            cat = f["failure_category"]
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        category_breakdown = [
            {"category": cat, "count": cnt, "percentage": round((cnt / total_failures * 100), 1) if total_failures > 0 else 0.0}
            for cat, cnt in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)
        ]

        # Dangerous cases (High confidence + wrong) vs Missed Automation (Low confidence + correct)
        high_conf_wrong = [f for f in failures if f["failure_category"] in ["DUPLICATE_FALSE_POSITIVE", "CONTRADICTED_CLAIM"]]
        missed_automation = [f for f in failures if f["failed_stage"] == "CALIBRATION"]

        return {
            "total_failure_count": total_failures,
            "failure_count_by_stage": stage_counts,
            "failure_percentage_by_stage": stage_percentages,
            "top_failure_categories": category_breakdown,
            "high_confidence_wrong_cases": {
                "count": len(high_conf_wrong),
                "examples": high_conf_wrong[:3]
            },
            "missed_automation_cases": {
                "count": len(missed_automation),
                "examples": missed_automation[:3]
            },
            "retrieval_vs_generation_breakdown": {
                "retrieval_misses": stage_counts["RETRIEVAL"],
                "generation_faithfulness_failures": stage_counts["FAITHFULNESS"]
            },
            "all_failures": failures
        }
