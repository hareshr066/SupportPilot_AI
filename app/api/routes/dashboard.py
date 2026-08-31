import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc, or_

from app.database.session import get_db_session
from app.database.models import PipelineRun, Issue, Repository
from app.services.pipeline_orchestrator import replay_pipeline_run
from app.core.auth import get_current_user, UserIdentity

logger = logging.getLogger("supportpilot.api.dashboard")
router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard Operations"])


class DashboardSummaryResponse(BaseModel):
    total_tickets: int = 0
    analyzed_today: int = 0
    auto_resolution_recommendations: int = 0
    human_escalations: int = 0
    high_severity_tickets: int = 0
    average_pipeline_latency_ms: float = 0.0


class RecentRunItem(BaseModel):
    pipeline_run_id: str
    ticket_id: Optional[int] = None
    issue_number: Optional[int] = None
    title: str = "Support Ticket Analysis"
    repository_name: str = "Unknown"
    severity: str = "UNKNOWN"
    duplicate_detected: str = "NO"
    root_cause_cluster: str = "Unclustered"
    calibrated_confidence: float = 0.0
    final_decision: str = "HUMAN_ESCALATION"
    status: str = "SUCCEEDED"
    created_at: str = ""
    total_latency_ms: float = 0.0


@router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
    summary="Get Aggregated Operational Dashboard Metrics",
    description="Returns total analyzed tickets, today's count, auto-resolution vs escalation breakdowns, high severity count, and average pipeline latency."
)
def get_dashboard_summary(
    db: Session = Depends(get_db_session),
    current_user: UserIdentity = Depends(get_current_user)
) -> DashboardSummaryResponse:
    # Calculate start of today UTC
    now_utc = datetime.now(timezone.utc)
    today_start = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)

    # 1. Total runs
    total_tickets = db.scalar(select(func.count(PipelineRun.id))) or 0

    # 2. Analyzed today
    analyzed_today = db.scalar(
        select(func.count(PipelineRun.id)).where(PipelineRun.created_at >= today_start)
    ) or 0

    # 3. Auto resolution recommendations
    auto_res = db.scalar(
        select(func.count(PipelineRun.id)).where(
            or_(
                PipelineRun.final_decision == "AUTO_RESOLVE_RECOMMENDATION",
                PipelineRun.final_decision == "AUTO_RESOLVE"
            )
        )
    ) or 0

    # 4. Human escalations
    human_esc = db.scalar(
        select(func.count(PipelineRun.id)).where(
            or_(
                PipelineRun.final_decision == "HUMAN_ESCALATION",
                PipelineRun.status == "ESCALATED"
            )
        )
    ) or 0

    # 5. High severity tickets (from Issues or PipelineRun)
    high_sev = db.scalar(
        select(func.count(PipelineRun.id)).where(
            PipelineRun.calibrated_confidence > 0.0
        )
    ) or 0

    # 6. Average latency
    avg_latency = db.scalar(select(func.avg(PipelineRun.total_latency_ms))) or 0.0

    return DashboardSummaryResponse(
        total_tickets=total_tickets,
        analyzed_today=analyzed_today,
        auto_resolution_recommendations=auto_res,
        human_escalations=human_esc,
        high_severity_tickets=high_sev,
        average_pipeline_latency_ms=round(float(avg_latency), 2)
    )


@router.get(
    "/recent-runs",
    response_model=List[RecentRunItem],
    summary="Get Recent Pipeline Runs Table",
    description="Returns recent pipeline execution summaries including repository, severity, root cause, duplicate status, and decision."
)
def get_recent_runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repository_id: Optional[int] = Query(None),
    final_decision: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
    current_user: UserIdentity = Depends(get_current_user)
) -> List[RecentRunItem]:
    stmt = select(PipelineRun).order_by(desc(PipelineRun.id)).offset(offset).limit(limit)
    if repository_id is not None:
        stmt = stmt.join(Issue, PipelineRun.ticket_id == Issue.id, isouter=True).where(Issue.repository_id == repository_id)
    if final_decision:
        stmt = stmt.where(PipelineRun.final_decision == final_decision)

    runs = db.scalars(stmt).all()
    results = []

    for r in runs:
        # Reconstruct structured details via replay
        replayed = replay_pipeline_run(r.pipeline_run_id)
        
        issue_title = "Support Ticket Analysis"
        repo_name = "System Repository"
        issue_num = None
        sev_label = "NORMAL"
        dup_str = "NO"
        rc_cluster = "General"

        if r.ticket_id:
            issue_rec = db.scalar(select(Issue).where(Issue.id == r.ticket_id))
            if issue_rec:
                issue_title = issue_rec.title
                issue_num = issue_rec.issue_number
                repo_rec = db.scalar(select(Repository).where(Repository.id == issue_rec.repository_id))
                if repo_rec:
                    repo_name = repo_rec.full_name

        if replayed:
            if replayed.severity:
                sev_label = replayed.severity.get("predicted_severity") or replayed.severity.get("predicted_label") or sev_label
            if replayed.duplicate:
                is_dup = replayed.duplicate.get("is_duplicate", False)
                dup_str = "YES" if is_dup else "NO"
            if replayed.root_cause:
                rc_cluster = replayed.root_cause.get("cluster_name") or replayed.root_cause.get("predicted_cluster_id") or rc_cluster

        results.append(RecentRunItem(
            pipeline_run_id=r.pipeline_run_id,
            ticket_id=r.ticket_id,
            issue_number=issue_num,
            title=issue_title,
            repository_name=repo_name,
            severity=str(sev_label).upper(),
            duplicate_detected=dup_str,
            root_cause_cluster=str(rc_cluster),
            calibrated_confidence=round(float(r.calibrated_confidence or 0.0), 3),
            final_decision=r.final_decision or "HUMAN_ESCALATION",
            status=r.status,
            created_at=r.created_at.isoformat() if r.created_at else "",
            total_latency_ms=round(float(r.total_latency_ms or 0.0), 2)
        ))

    return results
