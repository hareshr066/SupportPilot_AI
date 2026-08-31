import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Request, Header, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.database.session import get_db_session
from app.schemas.api_schemas import WebhookResponse
from app.core.errors import APIException
from app.services.webhook_service import WebhookService

logger = logging.getLogger("supportpilot.api.webhooks")
router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post(
    "/github",
    response_model=WebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="GitHub Webhook Ingestion Endpoint"
)
async def github_webhook_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_delivery: Optional[str] = Header(None, alias="X-GitHub-Delivery"),
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    db: Session = Depends(get_db_session)
):
    """
    Receives and processes GitHub Webhook events.
    Verifies HMAC SHA-256 signature, ensures delivery idempotency,
    persists issue records, and triggers the SupportPilot AI pipeline.
    """
    if not x_github_delivery or not x_github_event:
        raise APIException(
            code="INVALID_INPUT",
            message="Missing required GitHub Webhook headers (X-GitHub-Delivery, X-GitHub-Event).",
            status_code=status.HTTP_400_BAD_REQUEST
        )

    # Read raw body for HMAC signature verification
    body_bytes = await request.body()

    webhook_service = WebhookService()
    if not webhook_service.verify_signature(body_bytes, x_hub_signature_256):
        raise APIException(
            code="UNAUTHORIZED",
            message="Invalid or missing GitHub webhook signature (X-Hub-Signature-256).",
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception as exc:
        raise APIException(
            code="INVALID_INPUT",
            message=f"Malformed JSON payload in webhook body: {exc}",
            status_code=status.HTTP_400_BAD_REQUEST
        )

    event_record, pipeline_run_id = webhook_service.process_webhook(
        delivery_id=x_github_delivery,
        event_type=x_github_event,
        payload=payload,
        db=db,
        background=True
    )

    return WebhookResponse(
        delivery_id=event_record.delivery_id,
        status=event_record.processing_status,
        event_type=event_record.event_type,
        action=event_record.action,
        pipeline_run_id=pipeline_run_id
    )
