import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from config import settings
from app.services.github_client import GitHubClient
from app.services.issue_cleaner import IssueCleaner, NormalizedIssue
from app.database.models import (
    Repository,
    User,
    Label,
    Issue,
    Comment,
    PullRequest,
    RepositorySyncRun,
)

logger = logging.getLogger("supportpilot.sync_service")


class SyncService:
    """
    Orchestrates historical and incremental synchronization of GitHub repositories
    into the PostgreSQL database.
    """

    def __init__(self, github_client: Optional[GitHubClient] = None):
        self.github_client = github_client or GitHubClient()
        self.cleaner = IssueCleaner()

    def sync_repository(
        self,
        repository_id: int,
        db: Session,
        max_issues: Optional[int] = None,
        sync_run_id: Optional[str] = None
    ) -> RepositorySyncRun:
        """
        Synchronizes issues, comments, labels, assignees, and pull requests
        for the given repository ID.

        Supports incremental sync: if repository.last_synced_at is present,
        fetches only issues updated since that timestamp.
        """
        db_repo = db.scalar(select(Repository).where(Repository.id == repository_id))
        if not db_repo:
            raise ValueError(f"Repository with ID {repository_id} not found.")

        run_id = sync_run_id or f"sync_{uuid.uuid4().hex[:12]}"
        sync_run = RepositorySyncRun(
            sync_run_id=run_id,
            repository_id=db_repo.id,
            status="RUNNING",
            started_at=datetime.now(timezone.utc),
            config_version="v1.0"
        )
        db.add(sync_run)
        db.commit()

        effective_max = max_issues or settings.github_sync_max_issues

        try:
            since_str = db_repo.last_synced_at.isoformat() if db_repo.last_synced_at else None
            logger.info(f"Starting sync for {db_repo.full_name} (run_id: {run_id}, since: {since_str}, max: {effective_max})")

            # 1. Fetch raw issues from GitHub REST API
            raw_issues = self.github_client.fetch_repository_issues(
                owner=db_repo.owner,
                repo=db_repo.name,
                state="all",
                since=since_str,
                max_issues=effective_max
            )

            issues_count = 0
            comments_count = 0
            prs_count = 0

            # Caches to minimize DB roundtrips
            users_cache: Dict[str, User] = {}
            labels_cache: Dict[str, Label] = {}
            prs_cache: Dict[int, PullRequest] = {}

            existing_users = db.scalars(select(User)).all()
            for u in existing_users:
                users_cache[u.login.lower()] = u

            existing_labels = db.scalars(select(Label).where(Label.repository_id == db_repo.id)).all()
            for l in existing_labels:
                labels_cache[l.name] = l

            existing_prs = db.scalars(select(PullRequest).where(PullRequest.repository_id == db_repo.id)).all()
            for pr in existing_prs:
                prs_cache[pr.pr_number] = pr

            for raw_issue in raw_issues:
                # GitHub issues API returns pull requests too; filter or handle PR links
                is_pr = "pull_request" in raw_issue and raw_issue["pull_request"] is not None
                if is_pr and not settings.github_sync_include_pull_requests:
                    continue

                issue_num = raw_issue.get("number")
                comments_override: Optional[List[Dict[str, Any]]] = None

                # Fetch comments if configured and issue has comments
                if settings.github_sync_include_comments and raw_issue.get("comments", 0) > 0 and issue_num:
                    try:
                        comments_override = self.github_client.fetch_issue_comments(
                            owner=db_repo.owner,
                            repo=db_repo.name,
                            issue_number=issue_num,
                            max_comments=settings.github_max_comments_per_issue
                        )
                    except Exception as c_err:
                        logger.warning(f"Could not fetch comments for issue #{issue_num}: {c_err}")

                # Transform raw GitHub data to Silver schema
                transformed = self.cleaner._transform_single_issue(
                    raw_issue,
                    repository_name=db_repo.full_name,
                    comments_override=comments_override
                )

                try:
                    validated = NormalizedIssue.model_validate(transformed)
                except Exception as val_err:
                    logger.warning(f"Skipping invalid issue payload #{issue_num}: {val_err}")
                    continue

                # Get or create Author User
                author_user: Optional[User] = None
                if validated.author:
                    author_user = self._get_or_create_user(db, users_cache, validated.author.login, validated.author.id)

                # Assignees
                assignee_users: List[User] = []
                for ass in validated.assignees:
                    u = self._get_or_create_user(db, users_cache, ass.login, ass.id)
                    assignee_users.append(u)

                # Labels
                db_labels: List[Label] = []
                for label_name in validated.labels:
                    lbl = self._get_or_create_label(db, labels_cache, db_repo.id, label_name)
                    db_labels.append(lbl)

                # Linked PRs
                db_prs: List[PullRequest] = []
                for pr_model in validated.linked_pull_requests:
                    if pr_model.pr_number:
                        pr_entity = self._get_or_create_pr(db, prs_cache, db_repo.id, pr_model.pr_number, pr_model.html_url)
                        db_prs.append(pr_entity)
                        prs_count += 1

                created_dt = self._parse_dt(validated.created_at)
                updated_dt = self._parse_dt(validated.updated_at)
                closed_dt = self._parse_dt(validated.closed_at)

                # Upsert Issue
                existing_issue = db.scalar(
                    select(Issue).where(
                        Issue.repository_id == db_repo.id,
                        Issue.issue_number == validated.issue_number
                    )
                )

                if existing_issue:
                    existing_issue.title = validated.title
                    existing_issue.body = validated.body
                    existing_issue.state = validated.state
                    existing_issue.state_reason = validated.state_reason
                    existing_issue.author_id = author_user.id if author_user else None
                    existing_issue.created_at = created_dt or existing_issue.created_at
                    existing_issue.updated_at = updated_dt
                    existing_issue.closed_at = closed_dt
                    existing_issue.html_url = validated.html_url
                    existing_issue.duplicate_of_issue_number = validated.duplicate_of_issue_number
                    existing_issue.duplicate_detected = validated.duplicate_detected
                    db_issue = existing_issue
                else:
                    db_issue = Issue(
                        github_issue_id=validated.github_issue_id,
                        repository_id=db_repo.id,
                        issue_number=validated.issue_number,
                        title=validated.title,
                        body=validated.body,
                        state=validated.state,
                        state_reason=validated.state_reason,
                        author_id=author_user.id if author_user else None,
                        created_at=created_dt or datetime.now(timezone.utc),
                        updated_at=updated_dt,
                        closed_at=closed_dt,
                        html_url=validated.html_url,
                        duplicate_of_issue_number=validated.duplicate_of_issue_number,
                        duplicate_detected=validated.duplicate_detected
                    )
                    db.add(db_issue)
                    db.flush()

                db_issue.labels = db_labels
                db_issue.assignees = assignee_users
                db_issue.pull_requests = db_prs

                # Insert/Update Comments
                for c_model in validated.comments:
                    c_author: Optional[User] = None
                    if c_model.author:
                        c_author = self._get_or_create_user(db, users_cache, c_model.author.login, c_model.author.id)

                    c_created = self._parse_dt(c_model.created_at)
                    c_updated = self._parse_dt(c_model.updated_at)

                    if c_model.id:
                        existing_comment = db.scalar(select(Comment).where(Comment.github_comment_id == c_model.id))
                        if existing_comment:
                            existing_comment.body = c_model.body
                            existing_comment.author_id = c_author.id if c_author else None
                            existing_comment.updated_at = c_updated
                        else:
                            db.add(Comment(
                                github_comment_id=c_model.id,
                                issue_id=db_issue.id,
                                author_id=c_author.id if c_author else None,
                                body=c_model.body,
                                created_at=c_created,
                                updated_at=c_updated,
                                html_url=c_model.html_url
                            ))
                            comments_count += 1
                    else:
                        db.add(Comment(
                            issue_id=db_issue.id,
                            author_id=c_author.id if c_author else None,
                            body=c_model.body,
                            created_at=c_created,
                            updated_at=c_updated,
                            html_url=c_model.html_url
                        ))
                        comments_count += 1

                issues_count += 1

            now_dt = datetime.now(timezone.utc)
            db_repo.last_synced_at = now_dt
            sync_run.status = "COMPLETED"
            sync_run.completed_at = now_dt
            sync_run.issues_processed = issues_count
            sync_run.comments_processed = comments_count
            sync_run.pull_requests_processed = prs_count
            db.commit()

            logger.info(f"Sync completed successfully for {db_repo.full_name} ({issues_count} issues processed)")
            return sync_run

        except Exception as exc:
            db.rollback()
            sync_run.status = "FAILED"
            sync_run.completed_at = datetime.now(timezone.utc)
            sync_run.error_summary = str(exc)
            db.add(sync_run)
            db.commit()
            logger.error(f"Sync failed for repository {repository_id}: {exc}")
            return sync_run

    def _get_or_create_user(self, db: Session, cache: Dict[str, User], login: str, github_user_id: Optional[int]) -> User:
        key = login.lower()
        if key in cache:
            return cache[key]
        user = db.scalar(select(User).where(User.login == login))
        if not user:
            user = User(login=login, github_user_id=github_user_id)
            db.add(user)
            db.flush()
        cache[key] = user
        return user

    def _get_or_create_label(self, db: Session, cache: Dict[str, Label], repo_id: int, name: str) -> Label:
        if name in cache:
            return cache[name]
        label = db.scalar(select(Label).where(Label.repository_id == repo_id, Label.name == name))
        if not label:
            label = Label(repository_id=repo_id, name=name)
            db.add(label)
            db.flush()
        cache[name] = label
        return label

    def _get_or_create_pr(self, db: Session, cache: Dict[int, PullRequest], repo_id: int, pr_number: int, url: Optional[str]) -> PullRequest:
        if pr_number in cache:
            return cache[pr_number]
        pr = db.scalar(select(PullRequest).where(PullRequest.repository_id == repo_id, PullRequest.pr_number == pr_number))
        if not pr:
            pr = PullRequest(repository_id=repo_id, pr_number=pr_number, html_url=url)
            db.add(pr)
            db.flush()
        cache[pr_number] = pr
        return pr

    def _parse_dt(self, dt_str: Optional[str]) -> Optional[datetime]:
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            return None
