import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock

from app.services.github_client import GitHubClient
from app.services.ingestion_service import IngestionService
from app.services.issue_cleaner import IssueCleaner, NormalizedIssue
from app.services.database_loader import DatabaseLoader
from scripts.data_quality_report import generate_quality_report


def test_github_client_fetch_issue_comments_pagination(monkeypatch):
    """1 & 2. Verify comment fetching pagination and page handling."""
    client = GitHubClient(token="mock_token")

    def mock_request(method, url, params=None, **kwargs):
        page = params.get("page", 1) if params else 1
        mock_resp = MagicMock()
        if page == 1:
            mock_resp.json.return_value = [
                {"id": 101, "body": "Comment 1", "user": {"login": "user1"}}
            ]
        else:
            mock_resp.json.return_value = []
        return mock_resp

    monkeypatch.setattr(client, "_request", mock_request)

    cmts = client.fetch_issue_comments("owner", "repo", 1)
    assert len(cmts) == 1
    assert cmts[0]["id"] == 101


def test_label_and_comment_preservation(tmp_path):
    """3 & 4. Verify labels and comments survive Bronze -> Silver normalization."""
    bronze_dir = tmp_path / "raw" / "github" / "test_owner" / "test_repo"
    bronze_dir.mkdir(parents=True)

    raw_issues = [
        {
            "id": 5001,
            "number": 12,
            "title": "Bug in editor",
            "body": "Editor freezes on paste.",
            "state": "open",
            "user": {"login": "reporter1"},
            "labels": [{"name": "bug"}, {"name": "priority:high"}],
            "comments": 1,
            "comments_data": [
                {
                    "id": 9001,
                    "user": {"login": "reviewer1"},
                    "body": "Duplicate of #10",
                    "created_at": "2026-02-01T12:00:00Z"
                }
            ],
            "created_at": "2026-02-01T10:00:00Z"
        }
    ]

    with open(bronze_dir / "issues.json", "w", encoding="utf-8") as f:
        json.dump(raw_issues, f)

    cleaner = IssueCleaner(
        raw_data_dir=str(tmp_path / "raw"),
        processed_data_dir=str(tmp_path / "processed")
    )
    report = cleaner.process_repository("test_owner", "test_repo")

    assert report["valid_issues"] == 1
    assert report["issues_with_labels"] == 1
    assert report["issues_with_comments"] == 1
    assert report["detected_duplicates_count"] == 1

    silver_file = tmp_path / "processed" / "github" / "test_owner" / "test_repo" / "issues.json"
    with open(silver_file, "r", encoding="utf-8") as f:
        silver = json.load(f)

    assert silver[0]["labels"] == ["bug", "priority:high"]
    assert len(silver[0]["comments"]) == 1
    assert silver[0]["comments"][0]["body"] == "Duplicate of #10"
    assert silver[0]["duplicate_of_issue_number"] == 10
    assert silver[0]["duplicate_detected"] is True


def test_duplicate_pattern_extraction_positive_and_negative():
    """5 & 6. Test deterministic duplicate extraction positive and negative patterns."""
    cleaner = IssueCleaner()

    # Positive pattern 1: "duplicate of #42"
    num, detected = cleaner._extract_duplicate_relationship(100, "Some body text", [{"body": "Duplicate of #42"}])
    assert num == 42
    assert detected is True

    # Positive pattern 2: "closing as duplicate of #55"
    num, detected = cleaner._extract_duplicate_relationship(100, "Closing as duplicate of #55", [])
    assert num == 55
    assert detected is True

    # Negative pattern: "see #42" or "fixed by #42" (not a duplicate)
    num, detected = cleaner._extract_duplicate_relationship(100, "Please see #42 for details", [{"body": "Fixed by #99"}])
    assert num is None
    assert detected is False

    # Avoid self reference: "duplicate of #100" when issue number is 100
    num, detected = cleaner._extract_duplicate_relationship(100, "Duplicate of #100", [])
    assert num is None
    assert detected is False


def test_data_quality_report_calculation(tmp_path):
    """7, 8, 9. Test Data Quality Report calculation."""
    proc_dir = tmp_path / "processed" / "github" / "owner" / "repo"
    proc_dir.mkdir(parents=True)

    records = [
        {
            "github_issue_id": 1,
            "repository": "owner/repo",
            "issue_number": 1,
            "title": "T1",
            "body": "Body text",
            "state": "closed",
            "state_reason": "completed",
            "author": {"login": "u1"},
            "labels": ["bug", "priority:high"],
            "assignees": [{"login": "dev1"}],
            "created_at": "2026-01-01T00:00:00Z",
            "comments_count": 1,
            "comments": [{"id": 1, "body": "c1"}],
            "linked_pull_requests": [{"pr_number": 10}],
            "html_url": "url",
            "duplicate_of_issue_number": 2,
            "duplicate_detected": True
        }
    ]

    with open(proc_dir / "issues.json", "w", encoding="utf-8") as f:
        json.dump(records, f)

    # Override processed_data_dir setting temporarily in test
    from config import settings
    orig_dir = settings.processed_data_dir
    try:
        settings.processed_data_dir = str(tmp_path / "processed")
        report = generate_quality_report("owner", "repo")

        assert report["total_issues"] == 1
        assert report["percentages"]["body_present_pct"] == 100.0
        assert report["percentages"]["labels_present_pct"] == 100.0
        assert report["percentages"]["comments_present_pct"] == 100.0
        assert report["percentages"]["duplicates_detected_pct"] == 100.0
        assert report["ground_truth_coverage"]["severity_classification"]["count"] == 1
    finally:
        settings.processed_data_dir = orig_dir
