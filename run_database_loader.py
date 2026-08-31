import sys
import logging
import argparse
from sqlalchemy import func, select

from config import settings
from app.database.init_db import init_db
from app.database.session import get_db
from app.database.models import (
    Repository,
    User,
    Label,
    Issue,
    Comment,
    PullRequest,
    issue_labels,
    issue_assignees,
    issue_pull_requests,
)
from app.services.database_loader import DatabaseLoader

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("run_database_loader")


def run_loader(owner: str = "microsoft", repo: str = "vscode") -> None:
    """
    Executes PostgreSQL database initialization and Silver dataset loading.
    """
    logger.info("Initializing PostgreSQL Data Layer...")
    logger.info(f"Target repository: {owner}/{repo}")
    logger.info(f"Database URL dialect: {settings.database_url.split('://')[0]}")

    try:
        # Ensure database tables exist
        init_db()

        # Execute Silver dataset loading
        loader = DatabaseLoader()
        report = loader.load_repository(owner=owner, repo=repo)

        logger.info("Silver-to-PostgreSQL loading completed successfully!")
        
        # Query database row counts for verification
        with get_db() as session:
            repo_count = session.scalar(select(func.count(Repository.id)))
            issue_count = session.scalar(select(func.count(Issue.id)))
            open_issues = session.scalar(select(func.count(Issue.id)).where(Issue.state == "open"))
            closed_issues = session.scalar(select(func.count(Issue.id)).where(Issue.state == "closed"))
            user_count = session.scalar(select(func.count(User.id)))
            label_count = session.scalar(select(func.count(Label.id)))
            comment_count = session.scalar(select(func.count(Comment.id)))
            pr_count = session.scalar(select(func.count(PullRequest.id)))
            issue_label_links = session.scalar(select(func.count()).select_from(issue_labels))
            issue_assignee_links = session.scalar(select(func.count()).select_from(issue_assignees))
            issue_pr_links = session.scalar(select(func.count()).select_from(issue_pull_requests))
            dup_detected_count = session.scalar(
                select(func.count(Issue.id)).where(Issue.duplicate_detected == True)
            )

        logger.info("==========================================")
        logger.info("  PostgreSQL Database Verification Stats  ")
        logger.info("==========================================")
        logger.info(f"  - Repositories: {repo_count}")
        logger.info(f"  - Issues Total: {issue_count}")
        logger.info(f"    * Open Issues: {open_issues}")
        logger.info(f"    * Closed Issues: {closed_issues}")
        logger.info(f"    * Duplicates Detected: {dup_detected_count}")
        logger.info(f"  - Users (Authors/Assignees): {user_count}")
        logger.info(f"  - Labels: {label_count}")
        logger.info(f"  - Comments: {comment_count}")
        logger.info(f"  - Pull Requests: {pr_count}")
        logger.info(f"  - Issue-Label Links: {issue_label_links}")
        logger.info(f"  - Issue-Assignee Links: {issue_assignee_links}")
        logger.info(f"  - Issue-PR Links: {issue_pr_links}")
        logger.info("==========================================")

    except Exception as exc:
        logger.error(f"Database loading failed fatally: {exc}", exc_info=True)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous Support Triage - PostgreSQL Database Loader")
    parser.add_argument("--owner", type=str, default="microsoft", help="GitHub repository owner (default: microsoft)")
    parser.add_argument("--repo", type=str, default="vscode", help="GitHub repository name (default: vscode)")
    
    args = parser.parse_args()
    run_loader(owner=args.owner, repo=args.repo)


if __name__ == "__main__":
    main()
