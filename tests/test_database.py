import pytest
import json
from pathlib import Path
from typing import Dict, Any, List
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker, Session

from app.database.models import (
    Base,
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
from app.database.init_db import init_db
from app.services.database_loader import DatabaseLoader

@pytest.fixture
def test_db_session():
    """
    Creates an isolated in-memory SQLite engine and session for database unit testing.
    """
    test_engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def sample_silver_records() -> List[Dict[str, Any]]:
    return [
        {
            "github_issue_id": 2001,
            "repository": "test_org/test_app",
            "issue_number": 101,
            "title": "Crash on launch when offline",
            "body": "App crashes immediately on startup without internet connection.",
            "state": "open",
            "state_reason": None,
            "author": {"login": "reporter_alpha", "id": 111},
            "labels": ["bug", "high-priority"],
            "assignees": [
                {"login": "dev_beta", "id": 222},
                {"login": "dev_gamma", "id": 333}
            ],
            "created_at": "2026-02-01T10:00:00+00:00",
            "updated_at": "2026-02-02T11:00:00+00:00",
            "closed_at": None,
            "comments_count": 1,
            "comments": [
                {
                    "id": 5001,
                    "author": {"login": "dev_beta", "id": 222},
                    "body": "Investigating network fallback logic.",
                    "created_at": "2026-02-01T10:30:00+00:00",
                    "updated_at": None,
                    "html_url": "https://github.com/test_org/test_app/issues/101#comment-5001"
                }
            ],
            "linked_pull_requests": [
                {
                    "pr_number": 102,
                    "url": "https://api.github.com/repos/test_org/test_app/pulls/102",
                    "html_url": "https://github.com/test_org/test_app/pull/102",
                    "repository": "test_org/test_app"
                }
            ],
            "html_url": "https://github.com/test_org/test_app/issues/101",
            "duplicate_of_issue_number": 90,
            "duplicate_detected": True
        }
    ]


def setup_silver_file(tmp_path: Path, owner: str, repo: str, records: List[Dict[str, Any]]) -> Path:
    proc_dir = tmp_path / "processed" / "github" / owner / repo
    proc_dir.mkdir(parents=True, exist_ok=True)
    silver_file = proc_dir / "issues.json"
    with open(silver_file, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    return silver_file


# ---------------------------------------------------------
# Test Cases
# ---------------------------------------------------------

def test_database_connection_and_table_creation(test_db_session):
    """1 & 2. Verify engine connection and table initialization."""
    # Queries system tables / counts on clean session
    repos = test_db_session.scalars(select(Repository)).all()
    assert repos == []


def test_repository_and_issue_insertion(test_db_session, tmp_path, sample_silver_records):
    """3 & 4. Verify Repository and Issue model insertion."""
    setup_silver_file(tmp_path, "test_org", "test_app", sample_silver_records)
    
    loader = DatabaseLoader(processed_data_dir=str(tmp_path / "processed"), db_session=test_db_session)
    report = loader.load_repository("test_org", "test_app")

    assert report["loaded_issues_count"] == 1

    repo = test_db_session.scalar(select(Repository).where(Repository.full_name == "test_org/test_app"))
    assert repo is not None
    assert repo.owner == "test_org"
    assert repo.name == "test_app"

    issue = test_db_session.scalar(select(Issue).where(Issue.issue_number == 101))
    assert issue is not None
    assert issue.github_issue_id == 2001
    assert issue.title == "Crash on launch when offline"
    assert issue.state == "open"
    assert issue.duplicate_detected is True
    assert issue.duplicate_of_issue_number == 90


def test_label_and_many_to_many_relationship(test_db_session, tmp_path, sample_silver_records):
    """5 & 6. Verify Label creation and issue-label many-to-many link."""
    setup_silver_file(tmp_path, "test_org", "test_app", sample_silver_records)

    loader = DatabaseLoader(processed_data_dir=str(tmp_path / "processed"), db_session=test_db_session)
    loader.load_repository("test_org", "test_app")

    labels = test_db_session.scalars(select(Label)).all()
    assert len(labels) == 2
    label_names = {l.name for l in labels}
    assert label_names == {"bug", "high-priority"}

    issue = test_db_session.scalar(select(Issue).where(Issue.issue_number == 101))
    assert len(issue.labels) == 2


def test_user_author_and_assignee_relationships(test_db_session, tmp_path, sample_silver_records):
    """7. Verify User author and assignees relationship."""
    setup_silver_file(tmp_path, "test_org", "test_app", sample_silver_records)

    loader = DatabaseLoader(processed_data_dir=str(tmp_path / "processed"), db_session=test_db_session)
    loader.load_repository("test_org", "test_app")

    users = test_db_session.scalars(select(User)).all()
    user_logins = {u.login for u in users}
    assert "reporter_alpha" in user_logins
    assert "dev_beta" in user_logins
    assert "dev_gamma" in user_logins

    issue = test_db_session.scalar(select(Issue).where(Issue.issue_number == 101))
    assert issue.author.login == "reporter_alpha"
    assert len(issue.assignees) == 2


def test_comment_insertion(test_db_session, tmp_path, sample_silver_records):
    """8. Verify Comment insertion and foreign key relationship."""
    setup_silver_file(tmp_path, "test_org", "test_app", sample_silver_records)

    loader = DatabaseLoader(processed_data_dir=str(tmp_path / "processed"), db_session=test_db_session)
    loader.load_repository("test_org", "test_app")

    comments = test_db_session.scalars(select(Comment)).all()
    assert len(comments) == 1
    assert comments[0].github_comment_id == 5001
    assert comments[0].author.login == "dev_beta"
    assert comments[0].body == "Investigating network fallback logic."


def test_pull_request_relationship(test_db_session, tmp_path, sample_silver_records):
    """9. Verify PullRequest insertion and many-to-many relationship with Issue."""
    setup_silver_file(tmp_path, "test_org", "test_app", sample_silver_records)

    loader = DatabaseLoader(processed_data_dir=str(tmp_path / "processed"), db_session=test_db_session)
    loader.load_repository("test_org", "test_app")

    prs = test_db_session.scalars(select(PullRequest)).all()
    assert len(prs) == 1
    assert prs[0].pr_number == 102

    issue = test_db_session.scalar(select(Issue).where(Issue.issue_number == 101))
    assert len(issue.pull_requests) == 1
    assert issue.pull_requests[0].pr_number == 102


def test_idempotent_loading(test_db_session, tmp_path, sample_silver_records):
    """10 & 11. Verify running loader twice does NOT duplicate rows."""
    setup_silver_file(tmp_path, "test_org", "test_app", sample_silver_records)

    loader = DatabaseLoader(processed_data_dir=str(tmp_path / "processed"), db_session=test_db_session)
    
    # Run 1
    loader.load_repository("test_org", "test_app")
    issue_count_1 = test_db_session.scalar(select(func.count(Issue.id)))
    comment_count_1 = test_db_session.scalar(select(func.count(Comment.id)))

    # Run 2
    loader.load_repository("test_org", "test_app")
    issue_count_2 = test_db_session.scalar(select(func.count(Issue.id)))
    comment_count_2 = test_db_session.scalar(select(func.count(Comment.id)))

    assert issue_count_1 == 1
    assert issue_count_2 == 1
    assert comment_count_1 == 1
    assert comment_count_2 == 1


def test_transaction_rollback_behavior(test_db_session):
    """12. Verify transaction rollback on exception."""
    try:
        with test_db_session.begin_nested():
            repo = Repository(owner="invalid_org", name="invalid_repo", full_name="invalid_org/invalid_repo")
            test_db_session.add(repo)
            test_db_session.flush()
            # Raise artificial error
            raise ValueError("Artificial Transaction Failure Test")
    except ValueError:
        test_db_session.rollback()

    repos = test_db_session.scalars(select(Repository).where(Repository.full_name == "invalid_org/invalid_repo")).all()
    assert len(repos) == 0
