import os
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from config import settings
from app.database.session import get_db_session
from app.schemas.api_schemas import HealthResponse, ReadinessResponse

logger = logging.getLogger("supportpilot.api.health")
router = APIRouter(tags=["Health & Readiness"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Lightweight service health check",
    description="Returns immediate 200 OK status indicating the FastAPI web app is running."
)
def get_health() -> HealthResponse:
    return HealthResponse(status="ok", service="supportpilot")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Comprehensive service readiness check",
    description="Validates database connectivity (SELECT 1), pgvector extension, and local ML configuration."
)
def get_readiness(
    response: Response,
    db: Session = Depends(get_db_session)
) -> ReadinessResponse:
    checks = {}
    is_ready = True

    # 1. Check PostgreSQL Database Connectivity
    try:
        db.execute(text("SELECT 1;"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.error(f"Readiness check failed for database: {exc}")
        checks["database"] = "unavailable"
        is_ready = False

    # 2. Check pgvector Extension Availability
    try:
        res = db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector';")).scalar()
        if res == 1:
            checks["pgvector"] = "ok"
        else:
            checks["pgvector"] = "not_installed"
    except Exception as exc:
        logger.warning(f"Readiness check warning for pgvector: {exc}")
        checks["pgvector"] = "unknown"

    # 3. Check ML Model Directory / Config
    try:
        model_path = Path(settings.severity_model_path)
        if model_path.exists() or settings.severity_model_name:
            checks["models"] = "ok"
        else:
            checks["models"] = "unavailable"
    except Exception as exc:
        logger.warning(f"Readiness check warning for models: {exc}")
        checks["models"] = "unknown"

    # 4. Check GitHub Authentication Status (Safe indicator, never exposes tokens)
    try:
        from app.services.github_client import GitHubClient
        gh_client = GitHubClient()
        checks["github"] = gh_client.get_auth_status_summary()
    except Exception as exc:
        logger.warning(f"Readiness check warning for github client: {exc}")
        checks["github"] = "unknown"

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="not_ready", checks=checks)

    return ReadinessResponse(status="ready", checks=checks)
