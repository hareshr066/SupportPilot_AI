import logging
from typing import Optional, Dict
from fastapi import APIRouter, Header, Depends, status

from app.schemas.api_schemas import TicketAnalyzeRequest
from app.schemas.pipeline_schemas import TicketInput, PipelineResult
from app.services.pipeline_orchestrator import run_support_pipeline, replay_pipeline_run
from app.core.auth import get_current_user, UserIdentity

logger = logging.getLogger("supportpilot.api.tickets")
router = APIRouter(prefix="/api/v1/tickets", tags=["Ticket Pipeline Analysis"])

# Simple in-memory idempotency cache mapping Idempotency-Key -> pipeline_run_id
_IDEMPOTENCY_CACHE: Dict[str, str] = {}


@router.post(
    "/analyze",
    response_model=PipelineResult,
    status_code=status.HTTP_200_OK,
    summary="Analyze Support Ticket via LangGraph Orchestration Pipeline",
    description="Submits a support ticket for deterministic AI triage, root-cause correlation, grounded resolution generation, claim verification, calibrated confidence, routing, and decision processing."
)
def analyze_ticket(
    req: TicketAnalyzeRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: UserIdentity = Depends(get_current_user)
) -> PipelineResult:
    # 1. Idempotency Check
    if idempotency_key:
        cached_run_id = _IDEMPOTENCY_CACHE.get(idempotency_key)
        if cached_run_id:
            logger.info(f"Idempotency cache hit for key '{idempotency_key}' -> pipeline_run_id '{cached_run_id}'")
            replayed = replay_pipeline_run(cached_run_id)
            if replayed:
                return replayed

    # 2. Convert Request to Core TicketInput
    ticket_inp = TicketInput(
        repository_id=req.repository_id,
        title=req.title,
        body=req.body or "",
        issue_number=req.issue_number
    )

    # 3. Invoke LangGraph Orchestration Pipeline
    result = run_support_pipeline(ticket_inp)

    # 4. Save Idempotency Mapping
    if idempotency_key and result and result.pipeline_run_id:
        _IDEMPOTENCY_CACHE[idempotency_key] = result.pipeline_run_id

    return result
