import os
import csv
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import EvaluationRunRecord, EvaluationMetricRecord, EvaluationFailureRecord
from app.evaluation.config import EvaluationConfig
from app.evaluation.dataset import EvaluationDatasetBuilder, EvaluationDatasetItem
from app.evaluation.evaluators.severity_evaluator import SeverityEvaluator
from app.evaluation.evaluators.duplicate_evaluator import DuplicateEvaluator
from app.evaluation.evaluators.root_cause_evaluator import RootCauseEvaluator
from app.evaluation.evaluators.retrieval_evaluator import RetrievalEvaluator
from app.evaluation.evaluators.resolution_evaluator import ResolutionEvaluator
from app.evaluation.evaluators.calibration_evaluator import CalibrationEvaluator
from app.evaluation.evaluators.routing_evaluator import RoutingEvaluator
from app.evaluation.evaluators.e2e_evaluator import EndToEndEvaluator
from app.evaluation.evaluators.failure_analyzer import FailureAnalyzer

logger = logging.getLogger(__name__)

class MasterEvaluationRunner:
    """
    Master Evaluation Orchestrator for SupportPilot.
    Executes reproducible temporal evaluation across all 7 pipeline stages + E2E,
    persists immutable evaluation records into PostgreSQL DB,
    and writes structured artifacts to artifacts/evaluation/<run_id>/.
    """

    def __init__(self, config: Optional[EvaluationConfig] = None):
        self.config = config or EvaluationConfig()
        self.dataset_builder = EvaluationDatasetBuilder(self.config)
        self.severity_evaluator = SeverityEvaluator()
        self.duplicate_evaluator = DuplicateEvaluator()
        self.root_cause_evaluator = RootCauseEvaluator()
        self.retrieval_evaluator = RetrievalEvaluator()
        self.resolution_evaluator = ResolutionEvaluator()
        self.calibration_evaluator = CalibrationEvaluator()
        self.routing_evaluator = RoutingEvaluator()
        self.e2e_evaluator = EndToEndEvaluator()
        self.failure_analyzer = FailureAnalyzer()

    def run_evaluation(
        self,
        repository_id: Optional[int] = None,
        target_stage: str = "all",
        evaluation_run_id: Optional[str] = None,
        db_session: Optional[Session] = None
    ) -> Dict[str, Any]:

        run_id = evaluation_run_id or f"eval_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Starting Master Evaluation Run '{run_id}' (target_stage='{target_stage}')...")

        def _execute(session: Session) -> Dict[str, Any]:
            # 1. Build dataset & temporal split
            dataset = self.dataset_builder.build_dataset(session, repository_id=repository_id)
            train_items, val_items, test_items, split_info = self.dataset_builder.create_temporal_split(dataset)

            stage_metrics: Dict[str, Any] = {}

            # 2. Stage 1 — Severity
            if target_stage in ["all", "severity"]:
                stage_metrics["severity"] = self.severity_evaluator.evaluate(test_items)

            # 3. Stage 2 — Duplicate
            if target_stage in ["all", "duplicate"]:
                stage_metrics["duplicate"] = self.duplicate_evaluator.evaluate_retrieval_and_classification(
                    val_items, test_items, self.config.duplicate_threshold_grid, session
                )

            # 4. Stage 3 — Root Cause
            if target_stage in ["all", "root_cause"]:
                repo_id = repository_id or (dataset[0].repository_id if dataset else 1)
                stage_metrics["root_cause"] = self.root_cause_evaluator.evaluate(test_items, repo_id, session)

            # 5. Stage 4 — Retrieval
            if target_stage in ["all", "retrieval"]:
                stage_metrics["retrieval"] = self.retrieval_evaluator.evaluate(test_items, session)

            # 6. Stage 5 — Resolution & Faithfulness
            if target_stage in ["all", "resolution"]:
                stage_metrics["resolution"] = self.resolution_evaluator.evaluate(test_items, session)

            # 7. Stage 6 — Calibration & Auto-Resolution
            if target_stage in ["all", "calibration"]:
                stage_metrics["calibration"] = self.calibration_evaluator.evaluate(val_items, test_items)

            # 8. Stage 7 — Routing
            if target_stage in ["all", "routing"]:
                stage_metrics["routing"] = self.routing_evaluator.evaluate(test_items, session)

            # 9. Failure Analysis
            failure_results = self.failure_analyzer.analyze_failures(test_items, stage_metrics)

            # 10. End-to-End Evaluation
            e2e_results = self.e2e_evaluator.evaluate(test_items, stage_metrics)
            stage_metrics["end_to_end"] = e2e_results

            # Build summary JSON for dashboard
            summary = {
                "evaluation_run_id": run_id,
                "dataset_version": self.config.dataset_version,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "total_tickets": len(dataset),
                "test_tickets": len(test_items),
                "severity_weighted_f1": stage_metrics.get("severity", {}).get("ml_classifier", {}).get("weighted_f1", "N/A"),
                "duplicate_f1": stage_metrics.get("duplicate", {}).get("test_classification", {}).get("f1_score", "N/A"),
                "retrieval_recall_at_5": stage_metrics.get("retrieval", {}).get("hybrid_retrieval", {}).get("recall_at_5", "N/A"),
                "retrieval_mrr": stage_metrics.get("retrieval", {}).get("hybrid_retrieval", {}).get("mrr", "N/A"),
                "faithfulness_rate": stage_metrics.get("resolution", {}).get("faithfulness_rate", "N/A"),
                "resolution_correctness": stage_metrics.get("resolution", {}).get("resolution_correctness_rate", "N/A"),
                "brier_score": stage_metrics.get("calibration", {}).get("brier_score", "N/A"),
                "ece_score": stage_metrics.get("calibration", {}).get("ece_score", "N/A"),
                "routing_top1_accuracy": stage_metrics.get("routing", {}).get("ml_router", {}).get("top_1_accuracy", "N/A"),
                "auto_resolution_coverage": e2e_results.get("auto_resolution_coverage", "N/A"),
                "false_auto_resolution_rate": e2e_results.get("false_auto_resolution_rate", "N/A"),
                "human_escalation_rate": e2e_results.get("human_escalation_rate", "N/A"),
                "status": "COMPLETED"
            }

            # 11. Persist to Database
            eval_record = EvaluationRunRecord(
                evaluation_run_id=run_id,
                created_at=datetime.now(timezone.utc),
                code_version=self.config.code_version,
                dataset_version=self.config.dataset_version,
                feature_version=self.config.feature_version,
                model_versions_json={
                    "severity": "distilbert-base-uncased",
                    "embedding": "all-MiniLM-L6-v2",
                    "confidence": "isotonic-regression-v1"
                },
                status="COMPLETED",
                summary_json=summary
            )
            session.add(eval_record)
            session.flush()

            # Save metric records
            for stage_name, res in stage_metrics.items():
                if isinstance(res, dict):
                    rec = EvaluationMetricRecord(
                        evaluation_run_id=run_id,
                        stage=stage_name.upper(),
                        metric_name=f"{stage_name}_summary",
                        metric_value=res.get("f1_score") or res.get("weighted_f1") or res.get("top_1_accuracy"),
                        sample_count=res.get("sample_count", len(test_items)),
                        details_json=res,
                        created_at=datetime.now(timezone.utc)
                    )
                    session.add(rec)

            # Save failure records
            for fail in failure_results.get("all_failures", []):
                f_rec = EvaluationFailureRecord(
                    evaluation_run_id=run_id,
                    ticket_id=fail.get("ticket_id"),
                    failed_stage=fail["failed_stage"],
                    failure_category=fail["failure_category"],
                    predicted_result=fail.get("predicted_result"),
                    ground_truth=fail.get("ground_truth"),
                    evidence_json=fail.get("evidence_json"),
                    reason_code=fail.get("reason_code", "FAILURE"),
                    created_at=datetime.now(timezone.utc)
                )
                session.add(f_rec)

            session.commit()

            # 12. Save Artifact Files to artifacts/evaluation/<run_id>/
            artifact_dir = os.path.join("artifacts", "evaluation", run_id)
            os.makedirs(artifact_dir, exist_ok=True)

            with open(os.path.join(artifact_dir, "summary.json"), "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)

            with open(os.path.join(artifact_dir, "stage_metrics.json"), "w", encoding="utf-8") as f:
                json.dump(stage_metrics, f, indent=2)

            with open(os.path.join(artifact_dir, "dataset_summary.json"), "w", encoding="utf-8") as f:
                json.dump(split_info, f, indent=2)

            with open(os.path.join(artifact_dir, "failure_analysis.json"), "w", encoding="utf-8") as f:
                json.dump(failure_results, f, indent=2)

            with open(os.path.join(artifact_dir, "latency_metrics.json"), "w", encoding="utf-8") as f:
                json.dump(e2e_results.get("latency_metrics", {}), f, indent=2)

            with open(os.path.join(artifact_dir, "severity_metrics.json"), "w", encoding="utf-8") as f:
                json.dump(stage_metrics.get("severity", {}), f, indent=2)

            with open(os.path.join(artifact_dir, "duplicate_metrics.json"), "w", encoding="utf-8") as f:
                json.dump(stage_metrics.get("duplicate", {}), f, indent=2)

            with open(os.path.join(artifact_dir, "retrieval_metrics.json"), "w", encoding="utf-8") as f:
                json.dump(stage_metrics.get("retrieval", {}), f, indent=2)

            with open(os.path.join(artifact_dir, "resolution_metrics.json"), "w", encoding="utf-8") as f:
                json.dump(stage_metrics.get("resolution", {}), f, indent=2)

            with open(os.path.join(artifact_dir, "calibration_metrics.json"), "w", encoding="utf-8") as f:
                json.dump(stage_metrics.get("calibration", {}), f, indent=2)

            with open(os.path.join(artifact_dir, "routing_metrics.json"), "w", encoding="utf-8") as f:
                json.dump(stage_metrics.get("routing", {}), f, indent=2)

            # Write failure_analysis.csv
            csv_path = os.path.join(artifact_dir, "failure_analysis.csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["ticket_id", "failed_stage", "failure_category", "reason_code"])
                for fail in failure_results.get("all_failures", []):
                    writer.writerow([
                        fail.get("ticket_id") or "N/A",
                        fail["failed_stage"],
                        fail["failure_category"],
                        fail.get("reason_code", "N/A")
                    ])

            # Write threshold_analysis.csv
            thresh_csv_path = os.path.join(artifact_dir, "threshold_analysis.csv")
            with open(thresh_csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["threshold", "coverage", "precision", "false_auto_resolution_rate", "human_review_rate"])
                grid = stage_metrics.get("calibration", {}).get("threshold_analysis_grid", [])
                for row in grid:
                    writer.writerow([
                        row.get("threshold"),
                        row.get("coverage"),
                        row.get("precision"),
                        row.get("false_auto_resolution_rate"),
                        row.get("human_review_rate")
                    ])

            logger.info(f"Master Evaluation Run '{run_id}' completed successfully! Artifacts written to '{artifact_dir}'.")
            return {
                "evaluation_run_id": run_id,
                "summary": summary,
                "stage_metrics": stage_metrics,
                "failure_analysis": failure_results,
                "artifact_directory": artifact_dir
            }

        if db_session:
            return _execute(db_session)
        else:
            with get_db() as session:
                return _execute(session)
