import sys
import logging
import argparse
from typing import Optional

from config import settings
from app.services.github_client import GitHubClient
from app.services.ingestion_service import IngestionService

# Configure logging for ingestion entry point
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("run_ingestion")

def run_ingestion(
    owner: str = "microsoft",
    repo: str = "vscode",
    state: str = "all",
    max_issues: Optional[int] = None,
    fetch_comments: bool = True,
    max_comments_per_issue: Optional[int] = None
) -> None:
    """
    Main ingestion execution workflow for the Bronze layer.

    Args:
        owner: GitHub repository owner/organization name.
        repo: GitHub repository name.
        state: Issue state filter ('open', 'closed', 'all').
        max_issues: Optional cap on the number of issues to fetch for test runs.
        fetch_comments: Whether to fetch issue comments.
        max_comments_per_issue: Max comments per issue.
    """
    logger.info("Initializing GitHub Data Ingestion Pipeline...")
    logger.info(f"Target repository: {owner}/{repo} (State: {state}, Max Issues: {max_issues})")
    logger.info(f"Raw data target directory: {settings.raw_data_dir}")

    try:
        # 1. Instantiate client and ingestion service
        client = GitHubClient()
        service = IngestionService(client=client)

        # 2. Execute repository issue ingestion
        metadata = service.ingest_repository(
            owner=owner,
            repo=repo,
            state=state,
            max_issues=max_issues,
            fetch_comments=fetch_comments,
            max_comments_per_issue=max_comments_per_issue
        )

        logger.info("Ingestion completed successfully!")
        logger.info(f"Metadata Summary: {metadata}")

    except Exception as exc:
        logger.error(f"Ingestion process failed fatally: {exc}", exc_info=True)
        sys.exit(1)

def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous Support Triage - GitHub Bronze Data Ingestion")
    parser.add_argument("--owner", type=str, default="microsoft", help="GitHub repository owner (default: microsoft)")
    parser.add_argument("--repo", type=str, default="vscode", help="GitHub repository name (default: vscode)")
    parser.add_argument("--state", type=str, default="all", choices=["open", "closed", "all"], help="Issue state filter (default: all)")
    parser.add_argument("--max-issues", type=int, default=settings.github_max_issues, help=f"Max issues limit (default: {settings.github_max_issues}, use 0 for unlimited)")
    parser.add_argument("--no-comments", action="store_true", help="Disable fetching issue comments")
    parser.add_argument("--max-comments-per-issue", type=int, default=settings.github_max_comments_per_issue, help=f"Max comments per issue (default: {settings.github_max_comments_per_issue})")
    
    args = parser.parse_args()
    
    max_issues = None if args.max_issues == 0 else args.max_issues
    run_ingestion(
        owner=args.owner,
        repo=args.repo,
        state=args.state,
        max_issues=max_issues,
        fetch_comments=not args.no_comments,
        max_comments_per_issue=args.max_comments_per_issue
    )

if __name__ == "__main__":
    main()
