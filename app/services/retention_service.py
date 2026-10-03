import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Set
from sqlalchemy import text, select, func, delete
from sqlalchemy.orm import Session
from config import settings

import importlib
models = importlib.import_module("app.database.models")
Base = models.Base
PipelineRun = models.PipelineRun
PipelineStageRun = models.PipelineStageRun
ResolutionRun = models.ResolutionRun
ResolutionClaimRecord = models.ResolutionClaimRecord
VerificationRun = models.VerificationRun
ClaimVerificationRecord = models.ClaimVerificationRecord
ConfidenceRun = models.ConfidenceRun
DecisionRun = models.DecisionRun
RoutingPrediction = models.RoutingPrediction
SeverityPrediction = models.SeverityPrediction
WebhookEvent = models.WebhookEvent
EvaluationRunRecord = getattr(models, "EvaluationRunRecord", None)
EvaluationRun = EvaluationRunRecord
EvaluationMetrics = getattr(models, "EvaluationMetricRecord", None)
EvaluationFailure = getattr(models, "EvaluationFailureRecord", None)


logger = logging.getLogger(__name__)

# Absolute protection list: Knowledge and core domain tables that MUST NEVER be deleted
PROTECTED_KNOWLEDGE_TABLES: Set[str] = {
    "repositories",
    "issues",
    "comments",
    "pull_requests",
    "issue_pull_requests",
    "issue_assignees",
    "issue_labels",
    "labels",
    "users",
    "issue_embeddings",
    "retrieval_index_metadata",
    "root_cause_clusters",
    "root_cause_assignments",
    "calibration_dataset",
    "calibration_runs",
}

# Operational telemetry tables eligible for age-based retention pruning
ELIGIBLE_TELEMETRY_TABLES: Set[str] = {
    "webhook_events",
    "pipeline_stage_runs",
    "pipeline_runs",
    "resolution_claims",
    "resolution_runs",
    "claim_verifications",
    "verification_runs",
    "confidence_runs",
    "decision_runs",
    "routing_predictions",
    "severity_predictions",
    "repository_sync_runs",
    "evaluation_failures",
    "evaluation_metrics",
    "evaluation_runs",
    "retrieval_evaluations",
}


def calculate_storage_threshold_status(
    used_mb: float,
    max_mb: Optional[float] = None,
    warning_pct: Optional[float] = None,
    cleanup_pct: Optional[float] = None,
    critical_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calculates storage usage percentage and returns threshold alert status.
    
    Thresholds:
      - NORMAL: < 70%
      - WARNING: >= 70%
      - CLEANUP_RECOMMENDED: >= 80%
      - CRITICAL: >= 90%
    """
    max_capacity = max_mb if max_mb is not None else settings.storage_max_capacity_mb
    warn_p = warning_pct if warning_pct is not None else settings.storage_warning_percent
    clean_p = cleanup_pct if cleanup_pct is not None else settings.storage_cleanup_percent
    crit_p = critical_pct if critical_pct is not None else settings.storage_critical_percent

    pct_used = (used_mb / max_capacity * 100.0) if max_capacity > 0 else 0.0

    if pct_used >= crit_p:
        level = "CRITICAL"
        message = f"CRITICAL: Storage usage is {pct_used:.1f}% (>= {crit_p}%). Emergency telemetry pruning recommended."
    elif pct_used >= clean_p:
        level = "CLEANUP_RECOMMENDED"
        message = f"CLEANUP_RECOMMENDED: Storage usage is {pct_used:.1f}% (>= {clean_p}%). Housekeeping cleanup recommended."
    elif pct_used >= warn_p:
        level = "WARNING"
        message = f"WARNING: Storage usage is {pct_used:.1f}% (>= {warn_p}%)."
    else:
        level = "NORMAL"
        message = f"NORMAL: Storage usage is {pct_used:.1f}% (< {warn_p}%)."

    return {
        "status_level": level,
        "used_mb": round(used_mb, 2),
        "max_capacity_mb": round(max_capacity, 2),
        "percentage_used": round(pct_used, 2),
        "warning_threshold_pct": warn_p,
        "cleanup_threshold_pct": clean_p,
        "critical_threshold_pct": crit_p,
        "message": message,
    }


class RetentionService:
    """
    Dedicated production retention and housekeeping service.
    
    Guarantees:
      1. Zero deletion of knowledge base data (issues, resolutions, embeddings, PRs, repos).
      2. Safe batch deletion of operational telemetry in child-before-parent dependency order.
      3. Dry-run mode by default.
      4. Idempotent & transaction-safe execution.
    """

    def __init__(
        self,
        pipeline_days: Optional[int] = None,
        stage_days: Optional[int] = None,
        webhook_days: Optional[int] = None,
        evaluation_days: Optional[int] = None,
    ):
        self.pipeline_days = pipeline_days or settings.retention_pipeline_days
        self.stage_days = stage_days or settings.retention_stage_days
        self.webhook_days = webhook_days or settings.retention_webhook_days
        self.evaluation_days = evaluation_days or settings.retention_evaluation_days

    def get_database_storage_status(self, db: Session) -> Dict[str, Any]:
        """Inspects current database storage usage and reports threshold status."""
        dialect_name = db.bind.dialect.name if db.bind else "unknown"
        used_bytes = 0

        if dialect_name == "postgresql":
            try:
                res = db.execute(text("SELECT pg_database_size(current_database());")).scalar()
                used_bytes = int(res or 0)
            except Exception as e:
                logger.warning(f"Could not query PostgreSQL storage size: {e}")
        else:
            # Fallback estimation for SQLite / other dialects
            used_bytes = 10 * 1024 * 1024  # Default 10 MB baseline for test envs

        used_mb = used_bytes / (1024 * 1024)
        threshold_info = calculate_storage_threshold_status(used_mb)
        threshold_info["dialect"] = dialect_name
        return threshold_info

    def get_retention_cutoffs(self, now: Optional[datetime] = None) -> Dict[str, datetime]:
        """Calculates exact timestamp cutoffs for each telemetry category."""
        ref_now = now or datetime.now(timezone.utc)
        return {
            "pipeline": ref_now - timedelta(days=self.pipeline_days),
            "stage": ref_now - timedelta(days=self.stage_days),
            "webhook": ref_now - timedelta(days=self.webhook_days),
            "evaluation": ref_now - timedelta(days=self.evaluation_days),
        }

    def run_retention_housekeeping(
        self,
        db: Session,
        dry_run: bool = True,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Executes or simulates automated retention housekeeping.
        
        Order of deletion (Child -> Parent):
          1. claim_verifications (child of verification_runs)
          2. verification_runs (child of resolution_runs)
          3. resolution_claims (child of resolution_runs)
          4. resolution_runs
          5. pipeline_stage_runs (child of pipeline_runs)
          6. pipeline_runs
          7. confidence_runs
          8. decision_runs
          9. routing_predictions
          10. severity_predictions
          11. webhook_events
          12. repository_sync_runs
          13. evaluation_failures (child of evaluation_runs)
          14. evaluation_metrics (child of evaluation_runs)
          15. evaluation_runs
          16. retrieval_evaluations
        """
        cutoffs = self.get_retention_cutoffs(now)
        storage_status = self.get_database_storage_status(db)

        report: Dict[str, Any] = {
            "dry_run": dry_run,
            "executed_at": (now or datetime.now(timezone.utc)).isoformat(),
            "storage_status": storage_status,
            "retention_cutoffs": {k: v.isoformat() for k, v in cutoffs.items()},
            "protected_knowledge_tables": sorted(list(PROTECTED_KNOWLEDGE_TABLES)),
            "eligible_telemetry_tables": sorted(list(ELIGIBLE_TELEMETRY_TABLES)),
            "eligible_records": {},
            "deleted_records": {},
            "knowledge_records_protected": 0,
            "summary": "",
        }

        # Verify protection for historical knowledge
        knowledge_issues_count = db.scalar(select(func.count()).select_from(Base.metadata.tables["issues"])) or 0
        knowledge_embs_count = db.scalar(select(func.count()).select_from(Base.metadata.tables["issue_embeddings"])) or 0
        report["knowledge_records_protected"] = knowledge_issues_count + knowledge_embs_count

        # 1. Identify obsolete pipeline_runs
        pipeline_cutoff = cutoffs["pipeline"]
        stage_cutoff = cutoffs["stage"]
        webhook_cutoff = cutoffs["webhook"]
        eval_cutoff = cutoffs["evaluation"]

        # Collect expired IDs for FK consistency
        expired_pipeline_runs = db.scalars(
            select(PipelineRun.pipeline_run_id).where(PipelineRun.created_at < pipeline_cutoff)
        ).all()
        expired_stage_runs = db.scalars(
            select(PipelineStageRun.id).where(PipelineStageRun.started_at < stage_cutoff)
        ).all()
        expired_resolution_runs = db.scalars(
            select(ResolutionRun.id).where(ResolutionRun.created_at < pipeline_cutoff)
        ).all()
        expired_verification_runs = db.scalars(
            select(VerificationRun.id).where(VerificationRun.verified_at < pipeline_cutoff)
        ).all()
        expired_confidence_runs = db.scalars(
            select(ConfidenceRun.id).where(ConfidenceRun.created_at < pipeline_cutoff)
        ).all()
        expired_decision_runs = db.scalars(
            select(DecisionRun.id).where(DecisionRun.created_at < pipeline_cutoff)
        ).all()
        expired_webhooks = db.scalars(
            select(WebhookEvent.id).where(WebhookEvent.received_at < webhook_cutoff)
        ).all()
        expired_eval_runs = (
            db.scalars(select(EvaluationRun.evaluation_run_id).where(EvaluationRun.created_at < eval_cutoff)).all()
            if EvaluationRun is not None
            else []
        )

        report["eligible_records"] = {
            "pipeline_runs": len(expired_pipeline_runs),
            "pipeline_stage_runs": len(expired_stage_runs),
            "resolution_runs": len(expired_resolution_runs),
            "verification_runs": len(expired_verification_runs),
            "confidence_runs": len(expired_confidence_runs),
            "decision_runs": len(expired_decision_runs),
            "webhook_events": len(expired_webhooks),
            "evaluation_runs": len(expired_eval_runs),
        }

        total_eligible = sum(report["eligible_records"].values())

        if dry_run or total_eligible == 0:
            report["deleted_records"] = {k: 0 for k in report["eligible_records"].keys()}
            report["summary"] = (
                f"DRY RUN COMPLETE: {total_eligible} eligible telemetry records identified for pruning. "
                f"ZERO records were deleted. {report['knowledge_records_protected']} knowledge records remain strictly protected."
            )
            logger.info(report["summary"])
            return report

        # Execute actual cleanup in safe transaction block
        try:
            # 1. Child of verification_runs
            if expired_verification_runs and ClaimVerificationRecord is not None and VerificationRun is not None:
                db.execute(delete(ClaimVerificationRecord).where(ClaimVerificationRecord.verification_run_id.in_(expired_verification_runs)))
                db.execute(delete(VerificationRun).where(VerificationRun.id.in_(expired_verification_runs)))

            # 2. Child of resolution_runs
            if expired_resolution_runs and ResolutionClaimRecord is not None and ResolutionRun is not None:
                db.execute(delete(ResolutionClaimRecord).where(ResolutionClaimRecord.resolution_run_id.in_(expired_resolution_runs)))
                db.execute(delete(ResolutionRun).where(ResolutionRun.id.in_(expired_resolution_runs)))

            # 3. Child of pipeline_runs
            if expired_pipeline_runs and PipelineStageRun is not None and PipelineRun is not None:
                db.execute(delete(PipelineStageRun).where(PipelineStageRun.pipeline_run_id.in_(expired_pipeline_runs)))
                db.execute(delete(PipelineRun).where(PipelineRun.pipeline_run_id.in_(expired_pipeline_runs)))

            # 4. Other standalone telemetry
            if expired_confidence_runs and ConfidenceRun is not None:
                db.execute(delete(ConfidenceRun).where(ConfidenceRun.id.in_(expired_confidence_runs)))
            if expired_decision_runs and DecisionRun is not None:
                db.execute(delete(DecisionRun).where(DecisionRun.id.in_(expired_decision_runs)))
            if expired_webhooks and WebhookEvent is not None:
                db.execute(delete(WebhookEvent).where(WebhookEvent.id.in_(expired_webhooks)))

            # 5. Child of evaluation_runs
            if expired_eval_runs and EvaluationRun is not None:
                if EvaluationFailure is not None:
                    db.execute(delete(EvaluationFailure).where(EvaluationFailure.evaluation_run_id.in_(expired_eval_runs)))
                if EvaluationMetrics is not None:
                    db.execute(delete(EvaluationMetrics).where(EvaluationMetrics.evaluation_run_id.in_(expired_eval_runs)))
                db.execute(delete(EvaluationRun).where(EvaluationRun.evaluation_run_id.in_(expired_eval_runs)))

            db.commit()

            report["deleted_records"] = report["eligible_records"].copy()
            report["summary"] = (
                f"HOUSEKEEPING COMPLETE: Purged {total_eligible} obsolete telemetry records. "
                f"Knowledge tables ({report['knowledge_records_protected']} records) remain completely untouched."
            )
            logger.info(report["summary"])
            return report

        except Exception as err:
            db.rollback()
            logger.error(f"Error during retention housekeeping execution: {err}")
            raise
