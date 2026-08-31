import sys
import logging
import argparse
from pathlib import Path

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.session import get_db
from app.database.models import Repository, Issue
from app.schemas.resolution_schemas import ResolutionRequest
from app.services.grounded_resolution_service import (
    GroundedResolutionService,
    render_human_readable_resolution,
)
from sqlalchemy import select

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("test_resolution_generation")


def main():
    parser = argparse.ArgumentParser(
        description="SupportPilot - Grounded Resolution Generation Test CLI"
    )
    parser.add_argument("--owner", type=str, default="microsoft", help="Repository owner")
    parser.add_argument("--repo", type=str, default="vscode", help="Repository name")
    parser.add_argument("--issue-id", type=int, default=None, help="Database Issue ID to generate resolution for")
    parser.add_argument("--query", type=str, default=None, help="Raw ticket title/query text")
    parser.add_argument("--body", type=str, default="", help="Ticket body text")

    args = parser.parse_args()

    full_name = f"{args.owner}/{args.repo}"
    logger.info(f"Running Grounded Resolution Generation for repository: {full_name}")

    with get_db() as session:
        repo = session.scalar(
            select(Repository).where(Repository.full_name == full_name)
        )
        repo_id = repo.id if repo else None

        title = args.query
        body = args.body
        issue_number = None

        if args.issue_id:
            iss = session.get(Issue, args.issue_id)
            if iss:
                title = iss.title
                body = iss.body or ""
                issue_number = iss.issue_number
                repo_id = iss.repository_id
            else:
                logger.error(f"Issue ID {args.issue_id} not found.")
                sys.exit(1)

        if not title:
            title = "Terminal window crashes with ERR_CONNECTION_RESET on startup"
            body = "When starting bash shell in embedded terminal panel, connection resets immediately."
            logger.info(f"No ticket query supplied. Using default sample ticket: '{title}'")

        request = ResolutionRequest(
            title=title,
            body=body,
            repository_id=repo_id,
            issue_number=issue_number,
            severity_prediction="high",
            root_cause_cluster="terminal-crash"
        )

        service = GroundedResolutionService(db_session=session)
        resolution_res, evidence_pkg, run_id = service.generate_resolution(
            request=request,
            session=session
        )

        rendered = render_human_readable_resolution(resolution_res, evidence_pkg)
        print(rendered)


if __name__ == "__main__":
    main()
