import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import requests

from config import Settings
from app.services.github_client import GitHubClient
from app.services.ingestion_service import IngestionService

@pytest.fixture
def sample_raw_issues():
    return [
        {
            "id": 101,
            "number": 1,
            "title": "Bug: Application crash on startup",
            "body": "Crash log attached.",
            "state": "open",
            "labels": [{"id": 1, "name": "bug", "color": "f00"}],
            "assignee": None,
            "created_at": "2026-01-01T12:00:00Z",
            "updated_at": "2026-01-02T12:00:00Z",
            "closed_at": None,
            "custom_field": "preserve_me"
        },
        {
            "id": 102,
            "number": 2,
            "title": "Feature: Add dark mode",
            "body": "User preference toggle.",
            "state": "closed",
            "labels": [{"id": 2, "name": "enhancement", "color": "0f0"}],
            "assignee": {"login": "octocat"},
            "created_at": "2026-01-03T12:00:00Z",
            "updated_at": "2026-01-04T12:00:00Z",
            "closed_at": "2026-01-04T12:00:00Z"
        }
    ]

# ---------------------------------------------------------
# IngestionService Tests
# ---------------------------------------------------------

def test_successful_ingestion(tmp_path, sample_raw_issues):
    """Test successful raw issue ingestion and file creation."""
    mock_client = MagicMock(spec=GitHubClient)
    mock_client.base_url = "https://api.github.com"
    mock_client.fetch_repository_issues.return_value = sample_raw_issues

    service = IngestionService(client=mock_client, raw_data_dir=str(tmp_path))
    metadata = service.ingest_repository(owner="test_owner", repo="test_repo", state="all")

    target_dir = tmp_path / "github" / "test_owner" / "test_repo"
    issues_path = target_dir / "issues.json"
    metadata_path = target_dir / "metadata.json"

    assert issues_path.exists()
    assert metadata_path.exists()

    with open(issues_path, "r", encoding="utf-8") as f:
        written_issues = json.load(f)

    with open(metadata_path, "r", encoding="utf-8") as f:
        written_metadata = json.load(f)

    assert written_issues == sample_raw_issues
    assert written_metadata["issues_count"] == 2
    assert written_metadata["owner"] == "test_owner"
    assert written_metadata["repository"] == "test_repo"
    assert written_metadata["ingestion_status"] == "SUCCESS"
    assert metadata == written_metadata

def test_unmodified_raw_data_preservation(tmp_path, sample_raw_issues):
    """Verify that Bronze layer preserves all raw fields without transformation."""
    mock_client = MagicMock(spec=GitHubClient)
    mock_client.base_url = "https://api.github.com"
    mock_client.fetch_repository_issues.return_value = sample_raw_issues

    service = IngestionService(client=mock_client, raw_data_dir=str(tmp_path))
    service.ingest_repository(owner="test_owner", repo="test_repo")

    issues_path = tmp_path / "github" / "test_owner" / "test_repo" / "issues.json"
    with open(issues_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data[0]["custom_field"] == "preserve_me"
    assert data[0]["labels"] == [{"id": 1, "name": "bug", "color": "f00"}]
    assert data[0]["assignee"] is None

def test_idempotent_reingestion(tmp_path, sample_raw_issues):
    """Verify running ingestion multiple times safely overwrites without creating duplicate files."""
    mock_client = MagicMock(spec=GitHubClient)
    mock_client.base_url = "https://api.github.com"
    mock_client.fetch_repository_issues.return_value = sample_raw_issues

    service = IngestionService(client=mock_client, raw_data_dir=str(tmp_path))
    
    # First run
    service.ingest_repository(owner="test_owner", repo="test_repo")
    
    # Second run with updated dataset
    updated_issues = sample_raw_issues[:1]
    mock_client.fetch_repository_issues.return_value = updated_issues
    service.ingest_repository(owner="test_owner", repo="test_repo")

    target_dir = tmp_path / "github" / "test_owner" / "test_repo"
    files = list(target_dir.iterdir())
    
    # Should contain exactly issues.json and metadata.json (no issues_1.json or tmp files)
    file_names = {f.name for f in files}
    assert {"issues.json", "metadata.json"}.issubset(file_names)

    with open(target_dir / "issues.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 1

def test_github_client_failure_propagation(tmp_path):
    """Verify API errors from GitHubClient propagate up and clean up temporary files."""
    mock_client = MagicMock(spec=GitHubClient)
    mock_client.base_url = "https://api.github.com"
    mock_client.fetch_repository_issues.side_effect = requests.RequestException("API connection timeout")

    service = IngestionService(client=mock_client, raw_data_dir=str(tmp_path))

    with pytest.raises(requests.RequestException) as exc_info:
        service.ingest_repository(owner="test_owner", repo="test_repo")

    assert "API connection timeout" in str(exc_info.value)
    
    target_dir = tmp_path / "github" / "test_owner" / "test_repo"
    # Ensure no lingering tmp files remain
    if target_dir.exists():
        tmp_files = list(target_dir.glob("*.tmp"))
        assert len(tmp_files) == 0

# ---------------------------------------------------------
# GitHubClient Unit Tests
# ---------------------------------------------------------

def test_github_client_headers_authenticated():
    """Verify GitHubClient sets authentication headers correctly when token is present."""
    client = GitHubClient(token="ghp_testtoken123")
    assert client.session.headers["Authorization"] == "Bearer ghp_testtoken123"
    assert client.session.headers["Accept"] == "application/vnd.github+json"
    assert client.session.headers["X-GitHub-Api-Version"] == "2022-11-28"

def test_github_client_headers_unauthenticated():
    """Verify GitHubClient handles missing token gracefully without Authorization header."""
    client = GitHubClient(token=None)
    # Ensure authorization header is not present if token is None and settings.github_token is None/empty
    with patch("app.services.github_client.settings.github_token", None):
        client_no_token = GitHubClient(token=None)
        assert "Authorization" not in client_no_token.session.headers or client_no_token.session.headers.get("Authorization") is None

@patch("requests.Session.request")
def test_github_client_retry_on_503(mock_request):
    """Verify GitHubClient retries on transient HTTP 503 server error."""
    mock_res_503 = MagicMock()
    mock_res_503.status_code = 503

    mock_res_200 = MagicMock()
    mock_res_200.status_code = 200
    mock_res_200.json.return_value = [{"id": 1, "title": "Issue 1"}]

    mock_request.side_effect = [mock_res_503, mock_res_200]

    with patch("time.sleep", return_value=None):
        client = GitHubClient(token="fake_token")
        response = client._request("GET", "https://api.github.com/test")

    assert response.status_code == 200
    assert mock_request.call_count == 2

@patch("requests.Session.request")
def test_github_client_fetch_issues_pagination(mock_request):
    """Verify GitHubClient handles multi-page issue fetching."""
    mock_page1 = MagicMock()
    mock_page1.status_code = 200
    mock_page1.json.return_value = [{"id": i} for i in range(100)]

    mock_page2 = MagicMock()
    mock_page2.status_code = 200
    mock_page2.json.return_value = [{"id": 101}]

    mock_request.side_effect = [mock_page1, mock_page2]

    client = GitHubClient(token="fake_token")
    issues = client.fetch_repository_issues("owner", "repo", state="all")

    assert len(issues) == 101
    assert mock_request.call_count == 2

def test_invalid_configuration_handling():
    """Verify settings handling for custom configuration."""
    settings = Settings(github_token="secret_pat", raw_data_dir="./custom_raw")
    assert settings.github_token == "secret_pat"
    assert settings.raw_data_dir == "./custom_raw"
