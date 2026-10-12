import logging
import uuid
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set
from fastapi import APIRouter, Header, Depends, Query, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc

from config import settings
from app.database.session import get_db, get_db_session
from app.database.models import Issue, Repository, PipelineRun
from app.schemas.api_schemas import (
    TicketAnalyzeRequest,
    ExternalTicketCreate,
    ExternalTicketResponse,
)
from app.schemas.pipeline_schemas import TicketInput, PipelineResult
from app.services.pipeline_orchestrator import run_support_pipeline, replay_pipeline_run
from app.core.auth import get_current_user, UserIdentity
from app.core.errors import APIException

logger = logging.getLogger("supportpilot.api.tickets")
router = APIRouter(tags=["Tickets & Triage API"])

# In-memory idempotency cache mapping Idempotency-Key -> pipeline_run_id
_IDEMPOTENCY_CACHE: Dict[str, str] = {}

# In-memory ticket creation idempotency cache mapping Idempotency-Key -> ticket DB ID
_TICKET_IDEMPOTENCY_CACHE: Dict[str, int] = {}

# In-flight analysis tracking to prevent concurrent duplicate runs on the same ticket
_IN_FLIGHT_ANALYSES: Set[int] = set()
_IN_FLIGHT_LOCK = threading.Lock()


def trigger_automatic_ticket_analysis(
    ticket_id: int,
    repository_id: int,
    title: str,
    body: str,
    issue_number: int,
    idempotency_key: Optional[str] = None,
) -> None:
    """
    Executes the LangGraph triage & resolution pipeline in the background for a newly committed ticket.
    Protects against duplicate runs via an in-flight lock and database checks.
    Logs exceptions with full stack trace and records failure in PipelineRun without altering the ticket.
    """
    with _IN_FLIGHT_LOCK:
        if ticket_id in _IN_FLIGHT_ANALYSES:
            logger.warning(
                f"[Auto-Analysis] Ticket SP-{ticket_id} analysis is already in-flight. Skipping duplicate trigger."
            )
            return
        _IN_FLIGHT_ANALYSES.add(ticket_id)

    try:
        # Check if already analyzed or in-progress in DB
        with get_db() as session:
            existing_run = session.scalar(
                select(PipelineRun)
                .where(PipelineRun.ticket_id == ticket_id)
                .where(PipelineRun.status.in_(["RUNNING", "SUCCEEDED", "ESCALATED"]))
            )
            if existing_run:
                logger.info(
                    f"[Auto-Analysis] Ticket SP-{ticket_id} already has a pipeline run "
                    f"'{existing_run.pipeline_run_id}' with status '{existing_run.status}'. Skipping duplicate."
                )
                return

            if idempotency_key and idempotency_key in _IDEMPOTENCY_CACHE:
                logger.info(
                    f"[Auto-Analysis] Idempotency key '{idempotency_key}' already completed in "
                    f"pipeline run '{_IDEMPOTENCY_CACHE[idempotency_key]}'. Skipping duplicate."
                )
                return

        ticket_inp = TicketInput(
            ticket_id=ticket_id,
            repository_id=repository_id,
            title=title,
            body=body or "",
            issue_number=issue_number,
        )

        logger.info(
            f"[Auto-Analysis] Starting automatic AI analysis for ticket SP-{ticket_id} "
            f"(Repo: {repository_id}, Issue #{issue_number})"
        )

        result = run_support_pipeline(ticket_inp)

        if idempotency_key and result and result.pipeline_run_id:
            _IDEMPOTENCY_CACHE[idempotency_key] = result.pipeline_run_id

        logger.info(
            f"[Auto-Analysis] Successfully analyzed ticket SP-{ticket_id}: "
            f"run_id={result.pipeline_run_id}, status={result.status}, decision={result.final_decision}"
        )

    except Exception as exc:
        logger.exception(
            f"[Auto-Analysis] Failed executing automatic analysis for ticket SP-{ticket_id}: {exc}"
        )
        try:
            with get_db() as session:
                # Check if a PipelineRun was already created in initialize_ticket node
                running_run = session.scalar(
                    select(PipelineRun)
                    .where(PipelineRun.ticket_id == ticket_id)
                    .order_by(desc(PipelineRun.id))
                )
                now = datetime.now(timezone.utc)
                if running_run and running_run.status == "RUNNING":
                    running_run.status = "FAILED"
                    running_run.error_code = "AUTOMATIC_ANALYSIS_ERROR"
                    running_run.error_message = str(exc)[:1000]
                    running_run.completed_at = now
                elif not running_run:
                    failed_run = PipelineRun(
                        pipeline_run_id=f"pipeline_err_{uuid.uuid4().hex[:10]}",
                        ticket_id=ticket_id,
                        status="FAILED",
                        final_decision="HUMAN_ESCALATION",
                        recommended_team=settings.routing_default_queue,
                        total_latency_ms=0.0,
                        error_code="AUTOMATIC_ANALYSIS_ERROR",
                        error_message=str(exc)[:1000],
                        created_at=now,
                        completed_at=now,
                    )
                    session.add(failed_run)
                session.commit()
        except Exception as db_exc:
            logger.exception(
                f"[Auto-Analysis] Failed to persist FAILED status for ticket SP-{ticket_id}: {db_exc}"
            )
    finally:
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT_ANALYSES.discard(ticket_id)


def _get_or_create_app_repository(db: Session, app_name: str) -> Repository:
    """Finds or creates a target repository record for an application (e.g. StudySync)."""
    clean_app = (app_name or "StudySync").strip()
    full_name = f"{clean_app}/main"
    repo = db.scalar(select(Repository).where(Repository.full_name == full_name))
    if not repo:
        repo = Repository(
            owner=clean_app,
            name="main",
            full_name=full_name,
            html_url=f"https://github.com/{clean_app}/main",
            enabled=True,
            auto_analysis_enabled=True,
            created_at=datetime.now(timezone.utc)
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
    return repo


def _parse_ticket_id(ticket_id_str: str) -> int:
    """Parses numeric DB ID from public ticket string like 'SP-1042' or '1042'."""
    clean = str(ticket_id_str).strip().upper()
    if clean.startswith("SP-"):
        clean = clean[3:]
    try:
        val = int(clean)
        if val <= 0:
            raise ValueError()
        return val
    except ValueError:
        raise APIException(
            "INVALID_TICKET_ID",
            f"Invalid ticket identifier '{ticket_id_str}'. Expected format e.g. 'SP-1042' or '1042'.",
            status_code=status.HTTP_400_BAD_REQUEST
        )


@router.post(
    "",
    response_model=ExternalTicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Support Ticket",
    description="Validates and persists a support ticket from an external application (e.g. StudySync) into PostgreSQL, generating a stable public ticket ID (e.g. SP-1042)."
)
def create_ticket(
    req: ExternalTicketCreate,
    background_tasks: BackgroundTasks,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    current_user: UserIdentity = Depends(get_current_user)
) -> ExternalTicketResponse:
    effective_idemp = idempotency_key or req.external_ticket_id
    if effective_idemp and effective_idemp in _TICKET_IDEMPOTENCY_CACHE:
        cached_id = _TICKET_IDEMPOTENCY_CACHE[effective_idemp]
        existing_issue = db.scalar(select(Issue).where(Issue.id == cached_id))
        if existing_issue:
            logger.info(
                f"Idempotent ticket creation replay for key '{effective_idemp}' -> returning SP-{existing_issue.id}"
            )
            app_name = existing_issue.repository.owner if existing_issue.repository else (req.application or "StudySync")
            return ExternalTicketResponse(
                ticket_id=f"SP-{existing_issue.id}",
                status=existing_issue.state.upper() if existing_issue.state else "RECEIVED",
                application=app_name,
                title=existing_issue.title,
                description=existing_issue.body,
                created_at=existing_issue.created_at.isoformat() if existing_issue.created_at else None
            )

    repo = _get_or_create_app_repository(db, req.application)

    max_num = db.scalar(
        select(func.max(Issue.issue_number)).where(Issue.repository_id == repo.id)
    ) or 0
    next_num = max_num + 1

    now = datetime.now(timezone.utc)
    github_issue_id = int(now.timestamp() * 1000)

    issue = Issue(
        github_issue_id=github_issue_id,
        repository_id=repo.id,
        issue_number=next_num,
        title=req.title,
        body=req.description or "",
        state="RECEIVED",
        created_at=now,
        html_url=f"https://supportpilot.internal/tickets/SP-{next_num}",
        duplicate_detected=False
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)

    if effective_idemp:
        _TICKET_IDEMPOTENCY_CACHE[effective_idemp] = issue.id

    public_id = f"SP-{issue.id}"
    logger.info(f"Created ticket '{public_id}' for application '{req.application or 'StudySync'}' in database")

    # Initiate automatic analysis in the background without blocking ticket creation response
    if getattr(repo, "auto_analysis_enabled", True):
        background_tasks.add_task(
            trigger_automatic_ticket_analysis,
            ticket_id=issue.id,
            repository_id=repo.id,
            title=issue.title,
            body=issue.body,
            issue_number=issue.issue_number,
            idempotency_key=effective_idemp,
        )

    return ExternalTicketResponse(
        ticket_id=public_id,
        status="RECEIVED",
        application=req.application or "StudySync",
        title=issue.title,
        description=issue.body,
        created_at=issue.created_at.isoformat()
    )


@router.get(
    "",
    response_model=List[ExternalTicketResponse],
    summary="List Support Tickets",
    description="Returns a paginated list of support tickets persisted in PostgreSQL."
)
def list_tickets(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    application: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
    current_user: UserIdentity = Depends(get_current_user)
) -> List[ExternalTicketResponse]:
    stmt = select(Issue).order_by(desc(Issue.id)).offset(offset).limit(limit)
    if application:
        stmt = stmt.join(Repository, Issue.repository_id == Repository.id).where(
            func.lower(Repository.owner) == application.lower().strip()
        )

    issues = db.scalars(stmt).all()
    results = []
    for iss in issues:
        app_name = iss.repository.owner if iss.repository else "StudySync"
        results.append(ExternalTicketResponse(
            ticket_id=f"SP-{iss.id}",
            status=iss.state.upper() if iss.state else "RECEIVED",
            application=app_name,
            title=iss.title,
            description=iss.body,
            created_at=iss.created_at.isoformat() if iss.created_at else None
        ))
    return results


@router.get(
    "/{ticket_id}",
    response_model=ExternalTicketResponse,
    summary="Get Ticket Details by Ticket ID",
    description="Retrieves ticket metadata for a given ticket ID (e.g. SP-1042)."
)
def get_ticket(
    ticket_id: str,
    db: Session = Depends(get_db_session),
    current_user: UserIdentity = Depends(get_current_user)
) -> ExternalTicketResponse:
    db_id = _parse_ticket_id(ticket_id)
    issue = db.scalar(select(Issue).where(Issue.id == db_id))
    if not issue:
        raise APIException("NOT_FOUND", f"Ticket '{ticket_id}' not found.", status_code=status.HTTP_404_NOT_FOUND)

    app_name = issue.repository.owner if issue.repository else "StudySync"
    return ExternalTicketResponse(
        ticket_id=f"SP-{issue.id}",
        status=issue.state.upper() if issue.state else "RECEIVED",
        application=app_name,
        title=issue.title,
        description=issue.body,
        created_at=issue.created_at.isoformat() if issue.created_at else None
    )


@router.post(
    "/{ticket_id}/analyze",
    response_model=PipelineResult,
    status_code=status.HTTP_200_OK,
    summary="Analyze Existing Ticket via LangGraph Pipeline",
    description="Triggers the LangGraph orchestration pipeline for a persisted ticket identified by SP-1042."
)
def analyze_ticket_by_id(
    ticket_id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    current_user: UserIdentity = Depends(get_current_user)
) -> PipelineResult:
    db_id = _parse_ticket_id(ticket_id)
    issue = db.scalar(select(Issue).where(Issue.id == db_id))
    if not issue:
        raise APIException("NOT_FOUND", f"Ticket '{ticket_id}' not found.", status_code=status.HTTP_404_NOT_FOUND)

    if idempotency_key:
        cached_run_id = _IDEMPOTENCY_CACHE.get(idempotency_key)
        if cached_run_id:
            replayed = replay_pipeline_run(cached_run_id)
            if replayed:
                return replayed

    ticket_inp = TicketInput(
        ticket_id=issue.id,
        repository_id=issue.repository_id,
        title=issue.title,
        body=issue.body or "",
        issue_number=issue.issue_number
    )

    result = run_support_pipeline(ticket_inp)

    if idempotency_key and result and result.pipeline_run_id:
        _IDEMPOTENCY_CACHE[idempotency_key] = result.pipeline_run_id

    return result


@router.post(
    "/analyze",
    response_model=PipelineResult,
    status_code=status.HTTP_200_OK,
    summary="Analyze Ticket Payload via LangGraph Orchestration Pipeline",
    description="Submits an ad-hoc support ticket for AI triage and resolution processing."
)
def analyze_ticket_payload(
    req: TicketAnalyzeRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: UserIdentity = Depends(get_current_user)
) -> PipelineResult:
    if idempotency_key:
        cached_run_id = _IDEMPOTENCY_CACHE.get(idempotency_key)
        if cached_run_id:
            logger.info(f"Idempotency cache hit for key '{idempotency_key}' -> pipeline_run_id '{cached_run_id}'")
            replayed = replay_pipeline_run(cached_run_id)
            if replayed:
                return replayed

    ticket_inp = TicketInput(
        repository_id=req.repository_id,
        title=req.title,
        body=req.body or "",
        issue_number=req.issue_number
    )

    result = run_support_pipeline(ticket_inp)

    if idempotency_key and result and result.pipeline_run_id:
        _IDEMPOTENCY_CACHE[idempotency_key] = result.pipeline_run_id

    return result
