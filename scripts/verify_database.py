import sys
import logging
from pathlib import Path
from sqlalchemy import func, select

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
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

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("verify_database")

def verify_database() -> None:
    logger.info("Executing PostgreSQL Database Verification Queries...")

    with get_db() as session:
        # Row counts
        repos_count = session.scalar(select(func.count(Repository.id))) or 0
        issues_count = session.scalar(select(func.count(Issue.id))) or 0
        open_issues = session.scalar(select(func.count(Issue.id)).where(Issue.state == "open")) or 0
        closed_issues = session.scalar(select(func.count(Issue.id)).where(Issue.state == "closed")) or 0
        dup_detected_count = session.scalar(select(func.count(Issue.id)).where(Issue.duplicate_detected == True)) or 0
        users_count = session.scalar(select(func.count(User.id))) or 0
        labels_count = session.scalar(select(func.count(Label.id))) or 0
        comments_count = session.scalar(select(func.count(Comment.id))) or 0
        prs_count = session.scalar(select(func.count(PullRequest.id))) or 0
        issue_label_links = session.scalar(select(func.count()).select_from(issue_labels)) or 0
        issue_assignee_links = session.scalar(select(func.count()).select_from(issue_assignees)) or 0
        issue_pr_links = session.scalar(select(func.count()).select_from(issue_pull_requests)) or 0

        # Orphan checks
        # Orphaned issue_labels (links pointing to non-existent issue or label)
        orphaned_issue_labels = session.scalar(
            select(func.count())
            .select_from(issue_labels)
            .where(
                ~issue_labels.c.issue_id.in_(select(Issue.id)),
                ~issue_labels.c.label_id.in_(select(Label.id))
            )
        ) or 0

        # Orphaned comments
        orphaned_comments = session.scalar(
            select(func.count(Comment.id))
            .where(~Comment.issue_id.in_(select(Issue.id)))
        ) or 0

        # Orphaned issue_assignees
        orphaned_assignees = session.scalar(
            select(func.count())
            .select_from(issue_assignees)
            .where(
                ~issue_assignees.c.issue_id.in_(select(Issue.id)),
                ~issue_assignees.c.user_id.in_(select(User.id))
            )
        ) or 0

        # Orphaned issue_pull_requests
        orphaned_pr_links = session.scalar(
            select(func.count())
            .select_from(issue_pull_requests)
            .where(
                ~issue_pull_requests.c.issue_id.in_(select(Issue.id)),
                ~issue_pull_requests.c.pull_request_id.in_(select(PullRequest.id))
            )
        ) or 0

    logger.info("==========================================")
    logger.info("   PostgreSQL Database Verification Summary ")
    logger.info("==========================================")
    logger.info(f"  Repositories:                 {repos_count}")
    logger.info(f"  Issues (Total):              {issues_count}")
    logger.info(f"    - Open Issues:              {open_issues}")
    logger.info(f"    - Closed Issues:            {closed_issues}")
    logger.info(f"    - Duplicates Detected:      {dup_detected_count}")
    logger.info(f"  Users (Authors/Assignees):    {users_count}")
    logger.info(f"  Labels:                       {labels_count}")
    logger.info(f"  Comments:                     {comments_count}")
    logger.info(f"  Pull Requests:                {prs_count}")
    logger.info(f"  Issue-Label Relationships:    {issue_label_links}")
    logger.info(f"  Issue-Assignee Links:         {issue_assignee_links}")
    logger.info(f"  Issue-PR Relationships:       {issue_pr_links}")
    logger.info("------------------------------------------")
    logger.info(f"  Orphaned Issue-Labels:        {orphaned_issue_labels}")
    logger.info(f"  Orphaned Comments:            {orphaned_comments}")
    logger.info(f"  Orphaned Issue-Assignees:     {orphaned_assignees}")
    logger.info(f"  Orphaned Issue-PR Links:      {orphaned_pr_links}")
    logger.info("==========================================")

    if (
        orphaned_issue_labels == 0
        and orphaned_comments == 0
        and orphaned_assignees == 0
        and orphaned_pr_links == 0
    ):
        logger.info("All integrity checks PASSED. No orphaned records found!")
    else:
        logger.warning("WARNING: Data integrity check failed. Orphaned records detected.")

if __name__ == "__main__":
    verify_database()
