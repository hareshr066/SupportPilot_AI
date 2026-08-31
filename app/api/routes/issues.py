import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc, or_

from app.database.session import get_db_session
from app.database.models import Issue, Repository, Comment, PullRequest, SeverityPrediction, PipelineRun
from app.core.errors import APIException
from app.core.auth import get_current_user, UserIdentity

logger = logging.getLogger("supportpilot.api.issues")
router = APIRouter(prefix="/api/v1/issues", tags=["Issues Operations"])


class IssueListItem(BaseModel):
    id: int
    issue_number: int
    repository_id: int
    repository_name: str
    title: str
    body_snippet: str
    state: str
    created_at: str
    closed_at: Optional[str] = None
    html_url: str
    severity: str = "NORMAL"
    duplicate_detected: bool = False
    duplicate_of_issue_number: Optional[int] = None
    latest_run_id: Optional[str] = None
    latest_decision: Optional[str] = None


class IssueDetailResponse(BaseModel):
    id: int
    issue_number: int
    repository_id: int
    repository_name: str
    title: str
    body: str
    state: str
    created_at: str
    closed_at: Optional[str] = None
    html_url: str
    severity: str = "NORMAL"
    duplicate_detected: bool = False
    duplicate_of_issue_number: Optional[int] = None
    comments_count: int = 0
    comments: List[Dict[str, Any]] = []
    pull_requests: List[Dict[str, Any]] = []
    latest_run_id: Optional[str] = None
    latest_decision: Optional[str] = None


@router.get(
    "",
    response_model=Dict[str, Any],
    summary="List and Filter Database Issues",
    description="Returns a paginated list of ingested GitHub issues with state, repository, severity, and pipeline status filters."
)
def list_issues(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repository_id: Optional[int] = Query(None),
    state: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db_session)
):
    stmt = select(Issue).order_by(desc(Issue.created_at)).offset(offset).limit(limit)
    count_stmt = select(func.count(Issue.id))

    if repository_id is not None:
        stmt = stmt.where(Issue.repository_id == repository_id)
        count_stmt = count_stmt.where(Issue.repository_id == repository_id)

    if state is not None and state.strip():
        stmt = stmt.where(func.lower(Issue.state) == state.lower().strip())
        count_stmt = count_stmt.where(func.lower(Issue.state) == state.lower().strip())

    if search is not None and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(Issue.title.ilike(term), Issue.body.ilike(term)))
        count_stmt = count_stmt.where(or_(Issue.title.ilike(term), Issue.body.ilike(term)))

    issues = db.scalars(stmt).all()
    total_count = db.scalar(count_stmt) or 0

    results = []
    for iss in issues:
        repo_name = iss.repository.full_name if iss.repository else "Unknown"
        
        # Get severity
        sev_label = "NORMAL"
        if iss.severity_predictions:
            sev_label = iss.severity_predictions[0].predicted_label.upper()

        # Find latest pipeline run for this ticket
        latest_run = db.scalar(
            select(PipelineRun)
            .where(PipelineRun.ticket_id == iss.id)
            .order_by(desc(PipelineRun.id))
        )

        results.append(IssueListItem(
            id=iss.id,
            issue_number=iss.issue_number,
            repository_id=iss.repository_id,
            repository_name=repo_name,
            title=iss.title,
            body_snippet=iss.body[:250] if iss.body else "",
            state=iss.state.upper(),
            created_at=iss.created_at.isoformat() if iss.created_at else "",
            closed_at=iss.closed_at.isoformat() if iss.closed_at else None,
            html_url=iss.html_url,
            severity=sev_label,
            duplicate_detected=iss.duplicate_detected,
            duplicate_of_issue_number=iss.duplicate_of_issue_number,
            latest_run_id=latest_run.pipeline_run_id if latest_run else None,
            latest_decision=latest_run.final_decision if latest_run else None,
        ))

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "issues": [r.model_dump() for r in results]
    }


@router.get(
    "/{issue_id}",
    response_model=IssueDetailResponse,
    summary="Get Detailed Database Issue Record",
    description="Returns detailed issue record including body, comments, PR references, and pipeline execution links."
)
def get_issue_detail(
    issue_id: int,
    db: Session = Depends(get_db_session)
):
    iss = db.scalar(select(Issue).where(Issue.id == issue_id))
    if not iss:
        raise APIException("NOT_FOUND", f"Issue with ID '{issue_id}' not found.", status_code=status.HTTP_404_NOT_FOUND)

    repo_name = iss.repository.full_name if iss.repository else "Unknown"

    sev_label = "NORMAL"
    if iss.severity_predictions:
        sev_label = iss.severity_predictions[0].predicted_label.upper()

    latest_run = db.scalar(
        select(PipelineRun)
        .where(PipelineRun.ticket_id == iss.id)
        .order_by(desc(PipelineRun.id))
    )

    comments_data = []
    for c in iss.comments:
        comments_data.append({
            "id": c.id,
            "body": c.body,
            "created_at": c.created_at.isoformat() if c.created_at else "",
            "author": c.author.login if c.author else "ghost",
            "html_url": c.html_url
        })

    prs_data = []
    for pr in iss.pull_requests:
        prs_data.append({
            "id": pr.id,
            "pr_number": pr.pr_number,
            "html_url": pr.html_url
        })

    return IssueDetailResponse(
        id=iss.id,
        issue_number=iss.issue_number,
        repository_id=iss.repository_id,
        repository_name=repo_name,
        title=iss.title,
        body=iss.body or "",
        state=iss.state.upper(),
        created_at=iss.created_at.isoformat() if iss.created_at else "",
        closed_at=iss.closed_at.isoformat() if iss.closed_at else None,
        html_url=iss.html_url,
        severity=sev_label,
        duplicate_detected=iss.duplicate_detected,
        duplicate_of_issue_number=iss.duplicate_of_issue_number,
        comments_count=len(comments_data),
        comments=comments_data,
        pull_requests=prs_data,
        latest_run_id=latest_run.pipeline_run_id if latest_run else None,
        latest_decision=latest_run.final_decision if latest_run else None,
    )
