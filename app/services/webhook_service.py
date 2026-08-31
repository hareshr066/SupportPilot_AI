import hmac
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select

from config import settings
from app.database.models import Repository, Issue, WebhookEvent, User
from app.services.issue_cleaner import IssueCleaner, NormalizedIssue
from app.services.pipeline_orchestrator import run_support_pipeline

logger = logging.getLogger("supportpilot.webhook_service")


class WebhookService:
    """
    Handles GitHub Webhook signature verification, delivery idempotency,
    issue persistence, and pipeline trigger execution.
    """

    def __init__(self):
        self.cleaner = IssueCleaner()

    @staticmethod
    def verify_signature(payload_bytes: bytes, signature_header: Optional[str], secret: Optional[str] = None) -> bool:
        """
        Validates GitHub HMAC SHA-256 signature using constant-time comparison.
        Header format: 'sha256=<hex_digest>'
        """
        webhook_secret = secret or settings.github_webhook_secret
        if not webhook_secret:
            logger.warning("No GITHUB_WEBHOOK_SECRET configured. Rejecting webhook request.")
            return False

        if not signature_header:
            logger.warning("Missing X-Hub-Signature-256 header.")
            return False

        if not signature_header.startswith("sha256="):
            logger.warning("Malformed X-Hub-Signature-256 header (missing sha256= prefix).")
            return False

        expected_sig = signature_header[7:]
        computed_sig = hmac.new(
            webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(computed_sig, expected_sig)

    def process_webhook(
        self,
        delivery_id: str,
        event_type: str,
        payload: Dict[str, Any],
        db: Session,
        background: bool = True
    ) -> Tuple[WebhookEvent, Optional[str]]:
        """
        Processes a validated GitHub Webhook event.

        Returns:
            Tuple[WebhookEvent, Optional[str]]: (WebhookEvent DB record, pipeline_run_id if triggered)
        """
        # 1. Idempotency Check: check if delivery_id already exists in webhook_events
        existing_event = db.scalar(select(WebhookEvent).where(WebhookEvent.delivery_id == delivery_id))
        if existing_event:
            logger.info(f"Duplicate webhook delivery detected (delivery_id={delivery_id}). Skipping processing.")
            return existing_event, existing_event.pipeline_run_id

        # 2. Extract action & repository info
        action = payload.get("action")
        repo_data = payload.get("repository", {})
        repo_full_name = repo_data.get("full_name")

        db_repo: Optional[Repository] = None
        if repo_full_name:
            db_repo = db.scalar(select(Repository).where(Repository.full_name == repo_full_name))

        event_record = WebhookEvent(
            delivery_id=delivery_id,
            event_type=event_type,
            action=action,
            repository_id=db_repo.id if db_repo else None,
            processing_status="RECEIVED",
            received_at=datetime.now(timezone.utc),
            payload_summary={
                "event_type": event_type,
                "action": action,
                "repository": repo_full_name,
                "issue_number": payload.get("issue", {}).get("number")
            }
        )
        db.add(event_record)
        db.commit()

        # 3. Filter event type and action
        if event_type != "issues" or action not in ["opened", "reopened"]:
            logger.info(f"Ignoring non-trigger webhook event '{event_type}.{action}'.")
            event_record.processing_status = "IGNORED"
            db.commit()
            return event_record, None

        if not db_repo:
            logger.warning(f"Repository '{repo_full_name}' not registered in database. Event ignored.")
            event_record.processing_status = "FAILED"
            event_record.error_code = "REPOSITORY_NOT_REGISTERED"
            db.commit()
            return event_record, None

        # 4. Normalize & Persist Issue
        raw_issue = payload.get("issue")
        if not raw_issue:
            event_record.processing_status = "FAILED"
            event_record.error_code = "MISSING_ISSUE_PAYLOAD"
            db.commit()
            return event_record, None

        transformed = self.cleaner._transform_single_issue(raw_issue, db_repo.full_name)
        try:
            validated = NormalizedIssue.model_validate(transformed)
        except Exception as exc:
            logger.error(f"Failed to normalize webhook issue payload: {exc}")
            event_record.processing_status = "FAILED"
            event_record.error_code = "VALIDATION_FAILED"
            db.commit()
            return event_record, None

        # Upsert Author User
        author_user: Optional[User] = None
        if validated.author:
            author_user = db.scalar(select(User).where(User.login == validated.author.login))
            if not author_user:
                author_user = User(login=validated.author.login, github_user_id=validated.author.id)
                db.add(author_user)
                db.flush()

        # Upsert Issue
        db_issue = db.scalar(
            select(Issue).where(
                Issue.repository_id == db_repo.id,
                Issue.issue_number == validated.issue_number
            )
        )
        if db_issue:
            db_issue.title = validated.title
            db_issue.body = validated.body
            db_issue.state = validated.state
            db_issue.updated_at = datetime.now(timezone.utc)
        else:
            db_issue = Issue(
                github_issue_id=validated.github_issue_id,
                repository_id=db_repo.id,
                issue_number=validated.issue_number,
                title=validated.title,
                body=validated.body,
                state=validated.state,
                author_id=author_user.id if author_user else None,
                created_at=datetime.now(timezone.utc),
                html_url=validated.html_url
            )
            db.add(db_issue)
            db.flush()

        event_record.processing_status = "PROCESSING"
        db.commit()

        # 5. Trigger Pipeline if auto_analysis_enabled
        pipeline_run_id: Optional[str] = None
        if db_repo.auto_analysis_enabled:
            from app.services.pipeline_orchestrator import TicketInput
            ticket_input = TicketInput(
                repository_id=db_repo.id,
                issue_number=db_issue.issue_number,
                title=db_issue.title,
                body=db_issue.body or ""
            )
            try:
                pipeline_result = run_support_pipeline(ticket_input)
                pipeline_run_id = pipeline_result.pipeline_run_id
                event_record.pipeline_run_id = pipeline_run_id
                event_record.processing_status = "PROCESSED"
                db.commit()
                logger.info(f"Pipeline executed successfully for webhook delivery {delivery_id} (run_id: {pipeline_run_id})")
            except Exception as p_err:
                logger.error(f"Pipeline execution failed for webhook delivery {delivery_id}: {p_err}")
                event_record.processing_status = "FAILED"
                event_record.error_code = "PIPELINE_FAILED"
                db.commit()

        return event_record, pipeline_run_id
