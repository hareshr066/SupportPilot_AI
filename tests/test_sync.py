import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import create_app
from app.database.models import Base, Repository, Issue, Comment, Label, PullRequest, RepositorySyncRun
from app.database.session import get_db_session
from app.services.sync_service import SyncService

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


def override_get_db():
    db = TestingSessionLocal(bind=engine)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_db_session] = override_get_db
    with TestClient(app) as c:
        yield c


def test_repository_registration_and_list(client):
    with patch("app.services.github_client.GitHubClient.get_repository", return_value={"id": 1111, "html_url": "https://github.com/facebook/react"}):
        res = client.post("/api/v1/repositories", json={"owner": "facebook", "name": "react"})
        assert res.status_code == 201
        data = res.json()
        assert data["full_name"] == "facebook/react"
        repo_id = data["id"]

    # List repositories
    list_res = client.get("/api/v1/repositories")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # Get repository detail
    detail_res = client.get(f"/api/v1/repositories/{repo_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["owner"] == "facebook"


def test_historical_sync_service():
    with TestingSessionLocal(bind=engine) as db:
        repo = Repository(owner="golang", name="go", full_name="golang/go")
        db.add(repo)
        db.commit()
        repo_id = repo.id

    mock_raw_issues = [
        {
            "id": 5001,
            "number": 1,
            "title": "Compiler crash on type assertion",
            "body": "Duplicate of #2",
            "state": "closed",
            "created_at": "2026-01-01T00:00:00Z",
            "user": {"login": "gopher", "id": 10},
            "labels": [{"name": "bug"}, {"name": "compiler"}],
            "html_url": "https://github.com/golang/go/issues/1"
        },
        {
            "id": 5002,
            "number": 2,
            "title": "Root issue for compiler crash",
            "body": "Original issue report.",
            "state": "closed",
            "created_at": "2026-01-02T00:00:00Z",
            "user": {"login": "rob", "id": 11},
            "labels": [{"name": "bug"}],
            "html_url": "https://github.com/golang/go/issues/2"
        }
    ]

    mock_gh_client = MagicMock()
    mock_gh_client.fetch_repository_issues.return_value = mock_raw_issues
    mock_gh_client.fetch_issue_comments.return_value = []

    sync_service = SyncService(github_client=mock_gh_client)

    with TestingSessionLocal(bind=engine) as db:
        sync_run = sync_service.sync_repository(repo_id, db)
        assert sync_run.status == "COMPLETED"
        assert sync_run.issues_processed == 2

    # Verify Database persistence & duplicate detection
    with TestingSessionLocal(bind=engine) as db:
        issues = db.query(Issue).filter_by(repository_id=repo_id).all()
        assert len(issues) == 2
        dup_issue = db.query(Issue).filter_by(issue_number=1).first()
        assert dup_issue.duplicate_detected is True
        assert dup_issue.duplicate_of_issue_number == 2


def test_sync_repository_endpoint(client):
    with TestingSessionLocal(bind=engine) as db:
        repo = Repository(owner="python", name="cpython", full_name="python/cpython")
        db.add(repo)
        db.commit()
        repo_id = repo.id

    with patch("app.services.sync_service.SyncService.sync_repository"):
        res = client.post(f"/api/v1/repositories/{repo_id}/sync", json={"max_issues": 10})
        assert res.status_code == 202
        data = res.json()
        assert data["status"] == "PENDING"
        assert "sync_run_id" in data
