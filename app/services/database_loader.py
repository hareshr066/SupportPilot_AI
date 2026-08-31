import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from sqlalchemy.orm import Session
from sqlalchemy import select

from config import settings
from app.services.issue_cleaner import NormalizedIssue
from app.database.session import SessionLocal, get_db
from app.database.models import (
    Repository,
    User,
    Label,
    Issue,
    Comment,
    PullRequest,
)

logger = logging.getLogger(__name__)


class DatabaseLoader:
    """
    Service responsible for loading Silver normalized JSON issue datasets
    into PostgreSQL relational database tables using SQLAlchemy ORM.
    
    Idempotent: Running multiple times does not duplicate records.
    Transactional: Rolls back transaction on error.
    """

    def __init__(
        self,
        processed_data_dir: Optional[str] = None,
        db_session: Optional[Session] = None
    ):
        self.processed_data_dir = Path(processed_data_dir or settings.processed_data_dir)
        self._external_session = db_session

    def load_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """
        Loads the Silver dataset for <owner>/<repo> into PostgreSQL.
        """
        repository_name = f"{owner}/{repo}"
        logger.info(f"Starting PostgreSQL database loading for repository: {repository_name}")

        processed_file = (
            self.processed_data_dir / "github" / owner / repo / "issues.json"
        )
        if not processed_file.exists():
            fallback_file = self.processed_data_dir / owner / repo / "issues.json"
            if fallback_file.exists():
                processed_file = fallback_file
            else:
                err_msg = f"Silver dataset file not found at {processed_file}"
                logger.error(err_msg)
                raise FileNotFoundError(err_msg)

        with open(processed_file, "r", encoding="utf-8") as f:
            silver_records = json.load(f)

        if not isinstance(silver_records, list):
            raise ValueError(f"Invalid Silver dataset format in {processed_file}: expected array.")

        if self._external_session:
            return self._load_with_session(self._external_session, owner, repo, repository_name, silver_records)
        else:
            with get_db() as session:
                return self._load_with_session(session, owner, repo, repository_name, silver_records)

    def _load_with_session(
        self,
        session: Session,
        owner: str,
        repo: str,
        repository_name: str,
        silver_records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        
        # 1. Get or Create Repository
        db_repo = session.scalar(
            select(Repository).where(Repository.full_name == repository_name)
        )
        if not db_repo:
            db_repo = Repository(
                owner=owner,
                name=repo,
                full_name=repository_name,
                html_url=f"https://github.com/{repository_name}"
            )
            session.add(db_repo)
            session.flush()

        loaded_issues_count = 0
        skipped_issues_count = 0
        total_comments_count = 0
        total_prs_count = 0
        duplicate_detected_count = 0

        # Cache users, labels, PRs during batch run for performance
        users_cache: Dict[str, User] = {}
        labels_cache: Dict[str, Label] = {}
        prs_cache: Dict[int, PullRequest] = {}

        # Pre-populate cache from existing DB state for this repository
        existing_users = session.scalars(select(User)).all()
        for u in existing_users:
            users_cache[u.login.lower()] = u

        existing_labels = session.scalars(select(Label).where(Label.repository_id == db_repo.id)).all()
        for l in existing_labels:
            labels_cache[l.name] = l

        existing_prs = session.scalars(select(PullRequest).where(PullRequest.repository_id == db_repo.id)).all()
        for pr in existing_prs:
            prs_cache[pr.pr_number] = pr

        for record in silver_records:
            try:
                # Validate schema
                validated = NormalizedIssue.model_validate(record)
            except Exception as exc:
                skipped_issues_count += 1
                logger.warning(f"Skipping invalid Silver record in {repository_name}: {exc}")
                continue

            # 2. Get or Create Author User
            author_user: Optional[User] = None
            if validated.author:
                author_user = self._get_or_create_user(session, users_cache, validated.author.login, validated.author.id)

            # 3. Get or Create Assignee Users
            assignee_users: List[User] = []
            for ass in validated.assignees:
                u = self._get_or_create_user(session, users_cache, ass.login, ass.id)
                assignee_users.append(u)

            # 4. Get or Create Labels
            db_labels: List[Label] = []
            for label_name in validated.labels:
                lbl = self._get_or_create_label(session, labels_cache, db_repo.id, label_name)
                db_labels.append(lbl)

            # 5. Get or Create Pull Requests
            db_prs: List[PullRequest] = []
            for pr_model in validated.linked_pull_requests:
                if pr_model.pr_number:
                    pr_entity = self._get_or_create_pr(
                        session, prs_cache, db_repo.id, pr_model.pr_number, pr_model.html_url
                    )
                    db_prs.append(pr_entity)
                    total_prs_count += 1

            # Parse datetime helper
            created_dt = self._parse_dt(validated.created_at)
            updated_dt = self._parse_dt(validated.updated_at)
            closed_dt = self._parse_dt(validated.closed_at)

            # 6. Get or Create / Update Issue
            existing_issue = session.scalar(
                select(Issue).where(
                    Issue.repository_id == db_repo.id,
                    Issue.github_issue_id == validated.github_issue_id
                )
            )

            if not existing_issue:
                # Fallback check by repository_id & issue_number
                existing_issue = session.scalar(
                    select(Issue).where(
                        Issue.repository_id == db_repo.id,
                        Issue.issue_number == validated.issue_number
                    )
                )

            if existing_issue:
                # Update issue attributes
                existing_issue.title = validated.title
                existing_issue.body = validated.body
                existing_issue.state = validated.state
                existing_issue.state_reason = validated.state_reason
                existing_issue.author_id = author_user.id if author_user else None
                existing_issue.created_at = created_dt
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
                    created_at=created_dt,
                    updated_at=updated_dt,
                    closed_at=closed_dt,
                    html_url=validated.html_url,
                    duplicate_of_issue_number=validated.duplicate_of_issue_number,
                    duplicate_detected=validated.duplicate_detected
                )
                session.add(db_issue)
                session.flush()

            # Update relationships cleanly
            db_issue.labels = db_labels
            db_issue.assignees = assignee_users
            db_issue.pull_requests = db_prs

            if validated.duplicate_detected:
                duplicate_detected_count += 1

            # 7. Insert / Update Comments
            for c_model in validated.comments:
                c_author: Optional[User] = None
                if c_model.author:
                    c_author = self._get_or_create_user(session, users_cache, c_model.author.login, c_model.author.id)

                c_created = self._parse_dt(c_model.created_at)
                c_updated = self._parse_dt(c_model.updated_at)

                if c_model.id:
                    existing_comment = session.scalar(
                        select(Comment).where(Comment.github_comment_id == c_model.id)
                    )
                    if existing_comment:
                        existing_comment.body = c_model.body
                        existing_comment.author_id = c_author.id if c_author else None
                        existing_comment.updated_at = c_updated
                    else:
                        comment_obj = Comment(
                            github_comment_id=c_model.id,
                            issue_id=db_issue.id,
                            author_id=c_author.id if c_author else None,
                            body=c_model.body,
                            created_at=c_created,
                            updated_at=c_updated,
                            html_url=c_model.html_url
                        )
                        session.add(comment_obj)
                        total_comments_count += 1
                else:
                    comment_obj = Comment(
                        issue_id=db_issue.id,
                        author_id=c_author.id if c_author else None,
                        body=c_model.body,
                        created_at=c_created,
                        updated_at=c_updated,
                        html_url=c_model.html_url
                    )
                    session.add(comment_obj)
                    total_comments_count += 1

            loaded_issues_count += 1

        session.flush()

        logger.info(
            f"Successfully loaded Silver dataset into PostgreSQL for {repository_name}. "
            f"Issues Loaded/Updated: {loaded_issues_count}, Skipped: {skipped_issues_count}."
        )

        return {
            "repository": repository_name,
            "total_silver_issues": len(silver_records),
            "loaded_issues_count": loaded_issues_count,
            "skipped_issues_count": skipped_issues_count,
            "duplicate_detected_count": duplicate_detected_count,
        }

    def _get_or_create_user(
        self,
        session: Session,
        cache: Dict[str, User],
        login: str,
        github_user_id: Optional[int] = None
    ) -> User:
        login_key = login.lower()
        if login_key in cache:
            return cache[login_key]

        user = session.scalar(select(User).where(User.login == login))
        if not user:
            user = User(login=login, github_user_id=github_user_id)
            session.add(user)
            session.flush()

        cache[login_key] = user
        return user

    def _get_or_create_label(
        self,
        session: Session,
        cache: Dict[str, Label],
        repository_id: int,
        name: str
    ) -> Label:
        if name in cache:
            return cache[name]

        label = session.scalar(
            select(Label).where(
                Label.repository_id == repository_id,
                Label.name == name
            )
        )
        if not label:
            label = Label(repository_id=repository_id, name=name)
            session.add(label)
            session.flush()

        cache[name] = label
        return label

    def _get_or_create_pr(
        self,
        session: Session,
        cache: Dict[int, PullRequest],
        repository_id: int,
        pr_number: int,
        html_url: Optional[str]
    ) -> PullRequest:
        if pr_number in cache:
            return cache[pr_number]

        pr = session.scalar(
            select(PullRequest).where(
                PullRequest.repository_id == repository_id,
                PullRequest.pr_number == pr_number
            )
        )
        if not pr:
            pr = PullRequest(repository_id=repository_id, pr_number=pr_number, html_url=html_url)
            session.add(pr)
            session.flush()

        cache[pr_number] = pr
        return pr

    def _parse_dt(self, dt_str: Optional[str]) -> Optional[datetime]:
        if not dt_str:
            return None
        try:
            clean_str = dt_str.replace("Z", "+00:00")
            return datetime.fromisoformat(clean_str)
        except Exception:
            return None
