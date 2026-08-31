import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.database.session import get_db_session
from app.database.models import EvaluationRunRecord, EvaluationMetricRecord, EvaluationFailureRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/evaluations", tags=["Evaluations"])


@router.get("", response_model=Dict[str, Any])
def list_evaluations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session)
):
    """
    List all historical evaluation runs.
    """
    runs = db.scalars(
        select(EvaluationRunRecord)
        .order_by(desc(EvaluationRunRecord.created_at))
        .offset(offset)
        .limit(limit)
    ).all()

    total_count = db.scalar(select(EvaluationRunRecord).with_only_columns(EvaluationRunRecord.id)) or 0

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "evaluations": [
            {
                "evaluation_run_id": r.evaluation_run_id,
                "created_at": r.created_at.isoformat(),
                "dataset_version": r.dataset_version,
                "code_version": r.code_version,
                "status": r.status,
                "summary": r.summary_json
            }
            for r in runs
        ]
    }


@router.get("/{evaluation_run_id}", response_model=Dict[str, Any])
def get_evaluation_details(
    evaluation_run_id: str,
    db: Session = Depends(get_db_session)
):
    """
    Retrieve details and summary metrics for a specific evaluation run.
    """
    run_record = db.scalar(
        select(EvaluationRunRecord).where(EvaluationRunRecord.evaluation_run_id == evaluation_run_id)
    )
    if not run_record:
        raise HTTPException(status_code=404, detail=f"Evaluation run '{evaluation_run_id}' not found.")

    return {
        "evaluation_run_id": run_record.evaluation_run_id,
        "created_at": run_record.created_at.isoformat(),
        "dataset_version": run_record.dataset_version,
        "code_version": run_record.code_version,
        "feature_version": run_record.feature_version,
        "model_versions": run_record.model_versions_json,
        "status": run_record.status,
        "summary": run_record.summary_json
    }


@router.get("/{evaluation_run_id}/metrics", response_model=Dict[str, Any])
def get_evaluation_metrics(
    evaluation_run_id: str,
    db: Session = Depends(get_db_session)
):
    """
    Retrieve stage-by-stage evaluation metrics for a specific evaluation run.
    """
    metrics = db.scalars(
        select(EvaluationMetricRecord).where(EvaluationMetricRecord.evaluation_run_id == evaluation_run_id)
    ).all()

    stage_map: Dict[str, Any] = {}
    for m in metrics:
        stage_map[m.stage.lower()] = m.details_json

    return {
        "evaluation_run_id": evaluation_run_id,
        "stage_metrics": stage_map
    }


@router.get("/{evaluation_run_id}/failures", response_model=Dict[str, Any])
def get_evaluation_failures(
    evaluation_run_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_session)
):
    """
    Retrieve failure analysis cases for a specific evaluation run.
    """
    failures = db.scalars(
        select(EvaluationFailureRecord)
        .where(EvaluationFailureRecord.evaluation_run_id == evaluation_run_id)
        .limit(limit)
    ).all()

    return {
        "evaluation_run_id": evaluation_run_id,
        "total_failures": len(failures),
        "failures": [
            {
                "ticket_id": f.ticket_id,
                "failed_stage": f.failed_stage,
                "failure_category": f.failure_category,
                "reason_code": f.reason_code,
                "predicted_result": f.predicted_result,
                "ground_truth": f.ground_truth,
                "evidence": f.evidence_json
            }
            for f in failures
        ]
    }
