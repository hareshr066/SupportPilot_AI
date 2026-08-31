import pytest
from unittest.mock import MagicMock, patch
import requests
from app.services.github_client import GitHubClient


def test_github_client_init_headers():
    client = GitHubClient(token="test_token_123", base_url="https://api.github.com")
    assert client.session.headers["Authorization"] == "Bearer test_token_123"
    assert client.session.headers["Accept"] == "application/vnd.github+json"


def test_get_repository_success():
    client = GitHubClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": 12345, "name": "vscode", "full_name": "microsoft/vscode"}

    with patch.object(client.session, "request", return_value=mock_resp):
        repo = client.get_repository("microsoft", "vscode")
        assert repo["id"] == 12345
        assert repo["full_name"] == "microsoft/vscode"


def test_get_issue_success():
    client = GitHubClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": 999, "number": 42, "title": "Crash on launch"}

    with patch.object(client.session, "request", return_value=mock_resp):
        issue = client.get_issue("owner", "repo", 42)
        assert issue["number"] == 42
        assert issue["title"] == "Crash on launch"


def test_list_issues_pagination():
    client = GitHubClient()
    page1_resp = MagicMock()
    page1_resp.status_code = 200
    page1_resp.json.return_value = [{"id": 1, "number": 101}, {"id": 2, "number": 102}]

    page2_resp = MagicMock()
    page2_resp.status_code = 200
    page2_resp.json.return_value = []

    with patch.object(client.session, "request", side_effect=[page1_resp, page2_resp]):
        issues = client.fetch_repository_issues("owner", "repo", max_issues=10)
        assert len(issues) == 2
        assert issues[0]["number"] == 101


def test_rate_limit_retry():
    client = GitHubClient()
    rate_limit_resp = MagicMock()
    rate_limit_resp.status_code = 429
    rate_limit_resp.headers = {"X-RateLimit-Reset": "0"}

    success_resp = MagicMock()
    success_resp.status_code = 200
    success_resp.json.return_value = {"id": 1}

    with patch.object(client.session, "request", side_effect=[rate_limit_resp, success_resp]):
        with patch("time.sleep", return_value=None):
            res = client.get_repository("owner", "repo")
            assert res["id"] == 1


def test_transient_503_retry():
    client = GitHubClient()
    server_err_resp = MagicMock()
    server_err_resp.status_code = 503

    success_resp = MagicMock()
    success_resp.status_code = 200
    success_resp.json.return_value = {"id": 1}

    with patch.object(client.session, "request", side_effect=[server_err_resp, success_resp]):
        with patch("time.sleep", return_value=None):
            res = client.get_repository("owner", "repo")
            assert res["id"] == 1


def test_404_raises_http_error():
    client = GitHubClient()
    not_found_resp = MagicMock()
    not_found_resp.status_code = 404
    not_found_resp.raise_for_status.side_effect = requests.HTTPError("404 Not Found")

    with patch.object(client.session, "request", return_value=not_found_resp):
        with pytest.raises(requests.HTTPError):
            client.get_repository("owner", "nonexistent")
