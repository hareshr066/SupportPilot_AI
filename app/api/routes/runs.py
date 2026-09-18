import json
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database.session import get_db_session
from app.database.models import PipelineRun, PipelineStageRun
from app.schemas.pipeline_schemas import PipelineResult
from app.schemas.api_schemas import (
    PipelineRunSummaryResponse,
    PipelineStageRunResponse,
    EscalationPackageResponse,
    EvidenceSummaryResponse,
    EvidenceReferenceItem,
)
from app.services.pipeline_orchestrator import replay_pipeline_run
from app.core.errors import APIException
from app.core.auth import get_current_user, UserIdentity

from sqlalchemy import desc, func
from app.database.models import Issue, Repository
from fastapi import Query

logger = logging.getLogger("supportpilot.api.runs")
router = APIRouter(tags=["Pipeline Execution Query"])


@router.get(
    "",
    response_model=List[PipelineRunSummaryResponse],
    summary="List Pipeline Execution Runs",
    description="Returns a paginated list of pipeline runs."
)
def list_pipeline_runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repository_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    final_decision: Optional[str] = Query(None),
    db: Session = Depends(get_db_session)
):
    stmt = select(PipelineRun).order_by(desc(PipelineRun.id)).offset(offset).limit(limit)
    if repository_id is not None:
        stmt = stmt.join(Issue, PipelineRun.ticket_id == Issue.id, isouter=True).where(Issue.repository_id == repository_id)
    if status_filter:
        stmt = stmt.where(PipelineRun.status == status_filter)
    if final_decision:
        stmt = stmt.where(PipelineRun.final_decision == final_decision)

    runs = db.scalars(stmt).all()
    results = []
    for r in runs:
        results.append(PipelineRunSummaryResponse(
            pipeline_run_id=r.pipeline_run_id,
            ticket_id=r.ticket_id,
            status=r.status,
            final_decision=r.final_decision or "HUMAN_ESCALATION",
            recommended_team=r.recommended_team,
            calibrated_confidence=float(r.calibrated_confidence or 0.0),
            routing_probability=float(r.routing_probability or 0.0),
            total_latency_ms=float(r.total_latency_ms or 0.0),
            created_at=r.created_at.isoformat() if r.created_at else None
        ))
    return results


@router.get(
    "/{pipeline_run_id}",
    response_model=PipelineRunSummaryResponse,
    summary="Get Pipeline Run Status",
    description="Retrieves persisted high-level execution status, final decision, and latencies for a pipeline run."
)
def get_pipeline_run_status(
    pipeline_run_id: str,
    db: Session = Depends(get_db_session),
    current_user: UserIdentity = Depends(get_current_user)
) -> PipelineRunSummaryResponse:
    run_rec = db.scalar(select(PipelineRun).where(PipelineRun.pipeline_run_id == pipeline_run_id))
    if not run_rec:
        raise APIException("NOT_FOUND", f"Pipeline run '{pipeline_run_id}' not found.", status_code=status.HTTP_404_NOT_FOUND)

    return PipelineRunSummaryResponse(
        pipeline_run_id=run_rec.pipeline_run_id,
        ticket_id=run_rec.ticket_id,
        status=run_rec.status,
        final_decision=run_rec.final_decision,
        recommended_team=run_rec.recommended_team,
        calibrated_confidence=float(run_rec.calibrated_confidence or 0.0),
        routing_probability=float(run_rec.routing_probability or 0.0),
        total_latency_ms=float(run_rec.total_latency_ms or 0.0),
        created_at=run_rec.created_at.isoformat() if run_rec.created_at else None
    )


@router.get(
    "/{pipeline_run_id}/result",
    response_model=PipelineResult,
    summary="Get Full Structured Pipeline Result",
    description="Reconstructs and returns the full structured PipelineResult from the database audit trail."
)
def get_pipeline_run_result(
    pipeline_run_id: str,
    current_user: UserIdentity = Depends(get_current_user)
) -> PipelineResult:
    replayed = replay_pipeline_run(pipeline_run_id)
    if not replayed:
        raise APIException("NOT_FOUND", f"Pipeline run '{pipeline_run_id}' not found.", status_code=status.HTTP_404_NOT_FOUND)
    return replayed


@router.get(
    "/{pipeline_run_id}/stages",
    response_model=List[PipelineStageRunResponse],
    summary="Get Stage-by-Stage Latency & Status Breakdown",
    description="Returns detailed execution telemetries for every stage node in the LangGraph workflow."
)
def get_pipeline_run_stages(
    pipeline_run_id: str,
    db: Session = Depends(get_db_session),
    current_user: UserIdentity = Depends(get_current_user)
) -> List[PipelineStageRunResponse]:
    # Check pipeline exists
    run_rec = db.scalar(select(PipelineRun).where(PipelineRun.pipeline_run_id == pipeline_run_id))
    if not run_rec:
        raise APIException("NOT_FOUND", f"Pipeline run '{pipeline_run_id}' not found.", status_code=status.HTTP_404_NOT_FOUND)

    stage_recs = db.scalars(
        select(PipelineStageRun).where(PipelineStageRun.pipeline_run_id == pipeline_run_id).order_by(PipelineStageRun.id)
    ).all()

    results = []
    for stg in stage_recs:
        results.append(PipelineStageRunResponse(
            stage=stg.stage_name,
            status=stg.status,
            latency_ms=float(stg.latency_ms or 0.0),
            started_at=stg.started_at.isoformat() if stg.started_at else None,
            completed_at=stg.completed_at.isoformat() if stg.completed_at else None,
            error_code=stg.error_code,
            error_message=stg.error_message
        ))

    return results


@router.get(
    "/{pipeline_run_id}/escalation",
    response_model=EscalationPackageResponse,
    summary="Get Human Escalation Package",
    description="Retrieves structured escalation metadata, reason codes, and team routing if pipeline required human review."
)
def get_pipeline_run_escalation(
    pipeline_run_id: str,
    current_user: UserIdentity = Depends(get_current_user)
) -> EscalationPackageResponse:
    replayed = replay_pipeline_run(pipeline_run_id)
    if not replayed:
        raise APIException("NOT_FOUND", f"Pipeline run '{pipeline_run_id}' not found.", status_code=status.HTTP_404_NOT_FOUND)

    esc_pkg = replayed.escalation_package or {}
    is_escalated = replayed.human_review_required or (replayed.final_decision != "AUTO_RESOLVE_RECOMMENDATION")

    return EscalationPackageResponse(
        pipeline_run_id=replayed.pipeline_run_id,
        ticket_id=replayed.ticket_id,
        escalated=is_escalated,
        reason_codes=esc_pkg.get("reason_codes", []),
        suggested_team=esc_pkg.get("suggested_team", replayed.recommended_team),
        suggested_component=esc_pkg.get("suggested_component"),
        escalation_package=esc_pkg
    )


@router.get(
    "/{pipeline_run_id}/evidence",
    response_model=EvidenceSummaryResponse,
    summary="Get Traceable Evidence References",
    description="Retrieves historical retrieved evidence cases, similarity metrics, and verification references."
)
def get_pipeline_run_evidence(
    pipeline_run_id: str,
    current_user: UserIdentity = Depends(get_current_user)
) -> EvidenceSummaryResponse:
    replayed = replay_pipeline_run(pipeline_run_id)
    if not replayed:
        raise APIException("NOT_FOUND", f"Pipeline run '{pipeline_run_id}' not found.", status_code=status.HTTP_404_NOT_FOUND)

    ret_dict = replayed.retrieval or {}
    ver_dict = replayed.verification or {}
    raw_cases = ret_dict.get("retrieved_cases", [])

    ref_items = []
    for c in raw_cases:
        ref_items.append(EvidenceReferenceItem(
            issue_id=c.get("issue_id", 0),
            issue_number=c.get("issue_number"),
            title=c.get("title", ""),
            html_url=c.get("html_url"),
            dense_similarity=float(c.get("dense_similarity", 0.0)),
            bm25_score=float(c.get("bm25_score", 0.0)),
            rrf_score=float(c.get("rrf_score", 0.0)),
            evidence_text_snippet=c.get("resolution_evidence_snippet", c.get("body_snippet", ""))[:300]
        ))

    return EvidenceSummaryResponse(
        pipeline_run_id=replayed.pipeline_run_id,
        ticket_id=replayed.ticket_id,
        evidence_completeness=float(ret_dict.get("evidence_completeness", 0.0)),
        num_retrieved_cases=len(ref_items),
        retrieved_cases=ref_items,
        verification_summary=ver_dict
    )
