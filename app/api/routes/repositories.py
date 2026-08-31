import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, BackgroundTasks, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.database.session import get_db_session
from app.database.models import Repository, Issue, RepositorySyncRun
from app.schemas.api_schemas import (
    CreateRepositoryRequest,
    RepositoryResponse,
    SyncRepositoryRequest,
    SyncResponse,
    SyncStatusResponse,
)
from app.core.errors import APIException
from app.services.github_client import GitHubClient
from app.services.sync_service import SyncService

logger = logging.getLogger("supportpilot.api.repositories")
router = APIRouter(prefix="/api/v1", tags=["repositories"])


@router.post(
    "/repositories",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new GitHub repository"
)
def create_repository(
    payload: CreateRepositoryRequest,
    db: Session = Depends(get_db_session)
):
    full_name = f"{payload.owner}/{payload.name}".lower()

    # Check for existing repository
    existing = db.scalar(select(Repository).where(func.lower(Repository.full_name) == full_name))
    if existing:
        count = db.scalar(select(func.count(Issue.id)).where(Issue.repository_id == existing.id)) or 0
        return RepositoryResponse(
            id=existing.id,
            github_repository_id=existing.github_repository_id,
            owner=existing.owner,
            name=existing.name,
            full_name=existing.full_name,
            html_url=existing.html_url,
            enabled=existing.enabled,
            webhook_enabled=existing.webhook_enabled,
            auto_analysis_enabled=existing.auto_analysis_enabled,
            last_synced_at=existing.last_synced_at.isoformat() if existing.last_synced_at else None,
            issue_count=count,
            created_at=existing.created_at.isoformat() if existing.created_at else None
        )

    # Fetch GitHub metadata if available
    gh_client = GitHubClient()
    gh_id: Optional[int] = None
    html_url = f"https://github.com/{payload.owner}/{payload.name}"

    try:
        gh_data = gh_client.get_repository(payload.owner, payload.name)
        if isinstance(gh_data, dict):
            gh_id = gh_data.get("id")
            html_url = gh_data.get("html_url") or html_url
    except Exception as exc:
        logger.warning(f"Could not fetch GitHub metadata for {full_name}: {exc}")

    now_dt = datetime.now(timezone.utc)
    new_repo = Repository(
        github_repository_id=gh_id,
        owner=payload.owner,
        name=payload.name,
        full_name=f"{payload.owner}/{payload.name}",
        html_url=html_url,
        enabled=True,
        webhook_enabled=True,
        auto_analysis_enabled=True,
        created_at=now_dt,
        updated_at=now_dt
    )
    db.add(new_repo)
    db.commit()
    db.refresh(new_repo)

    return RepositoryResponse(
        id=new_repo.id,
        github_repository_id=new_repo.github_repository_id,
        owner=new_repo.owner,
        name=new_repo.name,
        full_name=new_repo.full_name,
        html_url=new_repo.html_url,
        enabled=new_repo.enabled,
        webhook_enabled=new_repo.webhook_enabled,
        auto_analysis_enabled=new_repo.auto_analysis_enabled,
        last_synced_at=None,
        issue_count=0,
        created_at=new_repo.created_at.isoformat() if new_repo.created_at else None
    )


@router.get(
    "/repositories",
    response_model=List[RepositoryResponse],
    summary="List all registered repositories"
)
def list_repositories(db: Session = Depends(get_db_session)):
    repos = db.scalars(select(Repository)).all()
    results: List[RepositoryResponse] = []
    for r in repos:
        count = db.scalar(select(func.count(Issue.id)).where(Issue.repository_id == r.id)) or 0
        results.append(RepositoryResponse(
            id=r.id,
            github_repository_id=r.github_repository_id,
            owner=r.owner,
            name=r.name,
            full_name=r.full_name,
            html_url=r.html_url,
            enabled=r.enabled,
            webhook_enabled=r.webhook_enabled,
            auto_analysis_enabled=r.auto_analysis_enabled,
            last_synced_at=r.last_synced_at.isoformat() if r.last_synced_at else None,
            issue_count=count,
            created_at=r.created_at.isoformat() if r.created_at else None
        ))
    return results


@router.get(
    "/repositories/{repository_id}",
    response_model=RepositoryResponse,
    summary="Get details for a registered repository"
)
def get_repository_details(repository_id: int, db: Session = Depends(get_db_session)):
    repo = db.scalar(select(Repository).where(Repository.id == repository_id))
    if not repo:
        raise APIException(
            code="NOT_FOUND",
            message=f"Repository with ID '{repository_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND
        )

    count = db.scalar(select(func.count(Issue.id)).where(Issue.repository_id == repo.id)) or 0
    return RepositoryResponse(
        id=repo.id,
        github_repository_id=repo.github_repository_id,
        owner=repo.owner,
        name=repo.name,
        full_name=repo.full_name,
        html_url=repo.html_url,
        enabled=repo.enabled,
        webhook_enabled=repo.webhook_enabled,
        auto_analysis_enabled=repo.auto_analysis_enabled,
        last_synced_at=repo.last_synced_at.isoformat() if repo.last_synced_at else None,
        issue_count=count,
        created_at=repo.created_at.isoformat() if repo.created_at else None
    )


def _run_background_sync(repository_id: int, max_issues: Optional[int], sync_run_id: str):
    """Background task worker for repository sync using an independent database session."""
    from app.database.session import SessionLocal
    with SessionLocal() as db:
        sync_service = SyncService()
        sync_service.sync_repository(repository_id, db, max_issues=max_issues, sync_run_id=sync_run_id)


@router.post(
    "/repositories/{repository_id}/sync",
    response_model=SyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger historical/incremental repository synchronization"
)
def sync_repository_endpoint(
    repository_id: int,
    payload: Optional[SyncRepositoryRequest] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db_session)
):
    repo = db.scalar(select(Repository).where(Repository.id == repository_id))
    if not repo:
        raise APIException(
            code="NOT_FOUND",
            message=f"Repository with ID '{repository_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND
        )

    sync_run_id = f"sync_{uuid.uuid4().hex[:12]}"
    max_issues = payload.max_issues if payload else None

    background_tasks.add_task(_run_background_sync, repository_id, max_issues, sync_run_id)

    return SyncResponse(
        sync_run_id=sync_run_id,
        repository_id=repository_id,
        status="PENDING",
        started_at=datetime.now(timezone.utc).isoformat()
    )


@router.get(
    "/sync-runs/{sync_run_id}",
    response_model=SyncStatusResponse,
    summary="Get status of a historical synchronization run"
)
def get_sync_run_status(sync_run_id: str, db: Session = Depends(get_db_session)):
    run = db.scalar(select(RepositorySyncRun).where(RepositorySyncRun.sync_run_id == sync_run_id))
    if not run:
        raise APIException(
            code="NOT_FOUND",
            message=f"Sync run '{sync_run_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND
        )

    return SyncStatusResponse(
        sync_run_id=run.sync_run_id,
        repository_id=run.repository_id,
        status=run.status,
        started_at=run.started_at.isoformat() if run.started_at else "",
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        issues_processed=run.issues_processed,
        comments_processed=run.comments_processed,
        pull_requests_processed=run.pull_requests_processed,
        error_summary=run.error_summary
    )
