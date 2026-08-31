import json
import pytest
from pathlib import Path
from typing import Dict, Any, List

from app.services.issue_cleaner import IssueCleaner, NormalizedIssue

@pytest.fixture
def sample_bronze_issues() -> List[Dict[str, Any]]:
    return [
        {
            "id": 1001,
            "number": 42,
            "title": "Terminal fails to start on Windows 11",
            "body": "Stack trace attached:\nTypeError: Cannot read properties of undefined.\nClosing as duplicate of #100.",
            "state": "closed",
            "state_reason": "completed",
            "user": {"login": "dev_user_1", "id": 501},
            "labels": [
                {"id": 1, "name": "bug"},
                {"id": 2, "name": "terminal"}
            ],
            "assignees": [
                {"login": "assignee_1", "id": 601},
                {"login": "assignee_2", "id": 602}
            ],
            "created_at": "2026-01-10T08:00:00Z",
            "updated_at": "2026-01-11T09:00:00Z",
            "closed_at": "2026-01-11T09:00:00Z",
            "comments": 2,
            "comments_data": [
                {
                    "id": 9001,
                    "user": {"login": "helper_bot", "id": 701},
                    "body": "Duplicate issue found.",
                    "created_at": "2026-01-10T08:30:00Z"
                }
            ],
            "pull_request": {
                "url": "https://api.github.com/repos/test_owner/test_repo/pulls/43",
                "html_url": "https://github.com/test_owner/test_repo/pull/43"
            },
            "html_url": "https://github.com/test_owner/test_repo/issues/42"
        },
        {
            "id": 1002,
            "number": 45,
            "title": "Feature request: Add dark high contrast theme",
            "body": None,  # Missing body
            "state": "open",
            "state_reason": None,
            "user": {"login": "designer_1", "id": 502},
            "labels": [],
            "assignees": [],  # Missing assignees
            "created_at": "2026-01-12T10:00:00Z",
            "updated_at": None,
            "closed_at": None,
            "comments": 0,
            "html_url": "https://github.com/test_owner/test_repo/issues/45"
        },
        {
            "id": 1003,
            "number": 50,
            "title": "Reference issue without duplicate relationship",
            "body": "Please see issue #42 and issue #45 for general context on this topic.",
            "state": "open",
            "state_reason": None,
            "user": {"login": "community_member", "id": 503},
            "labels": [{"name": "discussion"}],
            "assignees": [],
            "created_at": "2026-01-15T12:00:00Z",
            "comments": 0,
            "html_url": "https://github.com/test_owner/test_repo/issues/50"
        }
    ]


def setup_bronze_dir(tmp_path: Path, owner: str, repo: str, issues: List[Dict[str, Any]]) -> Path:
    raw_dir = tmp_path / "raw" / "github" / owner / repo
    raw_dir.mkdir(parents=True, exist_ok=True)
    issues_file = raw_dir / "issues.json"
    with open(issues_file, "w", encoding="utf-8") as f:
        json.dump(issues, f, indent=2)
    return raw_dir


# ---------------------------------------------------------
# Test Cases
# ---------------------------------------------------------

def test_normal_issue_transformation(tmp_path, sample_bronze_issues):
    """1. Test normal issue transformation to Silver schema."""
    setup_bronze_dir(tmp_path, "test_owner", "test_repo", sample_bronze_issues)

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    report = cleaner.process_repository("test_owner", "test_repo")

    assert report["total_raw_issues"] == 3
    assert report["valid_issues"] == 3
    assert report["invalid_issues"] == 0

    processed_file = tmp_path / "processed" / "github" / "test_owner" / "test_repo" / "issues.json"
    assert processed_file.exists()

    with open(processed_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    record_42 = records[0]
    assert record_42["github_issue_id"] == 1001
    assert record_42["issue_number"] == 42
    assert record_42["repository"] == "test_owner/test_repo"
    assert record_42["title"] == "Terminal fails to start on Windows 11"
    assert "TypeError: Cannot read properties of undefined." in record_42["body"]
    assert record_42["state"] == "closed"
    assert record_42["author"] == {"login": "dev_user_1", "id": 501}
    assert record_42["html_url"] == "https://github.com/test_owner/test_repo/issues/42"


def test_missing_body_handling(tmp_path, sample_bronze_issues):
    """2. Test missing/None body is converted to empty string without error."""
    setup_bronze_dir(tmp_path, "test_owner", "test_repo", sample_bronze_issues)

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    cleaner.process_repository("test_owner", "test_repo")

    processed_file = tmp_path / "processed" / "github" / "test_owner" / "test_repo" / "issues.json"
    with open(processed_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    record_45 = records[1]
    assert record_45["issue_number"] == 45
    assert record_45["body"] == ""


def test_missing_assignee_handling(tmp_path, sample_bronze_issues):
    """3. Test missing assignees returns empty list."""
    setup_bronze_dir(tmp_path, "test_owner", "test_repo", sample_bronze_issues)

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    cleaner.process_repository("test_owner", "test_repo")

    processed_file = tmp_path / "processed" / "github" / "test_owner" / "test_repo" / "issues.json"
    with open(processed_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    assert records[1]["assignees"] == []


def test_multiple_labels_normalization(tmp_path, sample_bronze_issues):
    """4. Test multiple nested labels converted to list of string names."""
    setup_bronze_dir(tmp_path, "test_owner", "test_repo", sample_bronze_issues)

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    cleaner.process_repository("test_owner", "test_repo")

    processed_file = tmp_path / "processed" / "github" / "test_owner" / "test_repo" / "issues.json"
    with open(processed_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    assert records[0]["labels"] == ["bug", "terminal"]


def test_multiple_assignees_normalization(tmp_path, sample_bronze_issues):
    """5. Test multiple assignees normalized correctly."""
    setup_bronze_dir(tmp_path, "test_owner", "test_repo", sample_bronze_issues)

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    cleaner.process_repository("test_owner", "test_repo")

    processed_file = tmp_path / "processed" / "github" / "test_owner" / "test_repo" / "issues.json"
    with open(processed_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    expected = [
        {"login": "assignee_1", "id": 601},
        {"login": "assignee_2", "id": 602}
    ]
    assert records[0]["assignees"] == expected


def test_comment_normalization(tmp_path, sample_bronze_issues):
    """6. Test structured comment list normalization."""
    setup_bronze_dir(tmp_path, "test_owner", "test_repo", sample_bronze_issues)

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    cleaner.process_repository("test_owner", "test_repo")

    processed_file = tmp_path / "processed" / "github" / "test_owner" / "test_repo" / "issues.json"
    with open(processed_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    record_42_comments = records[0]["comments"]
    assert len(record_42_comments) == 1
    assert record_42_comments[0]["id"] == 9001
    assert record_42_comments[0]["author"] == {"login": "helper_bot", "id": 701}
    assert record_42_comments[0]["body"] == "Duplicate issue found."


def test_timestamp_normalization(tmp_path, sample_bronze_issues):
    """7. Test timestamp ISO-8601 normalization."""
    setup_bronze_dir(tmp_path, "test_owner", "test_repo", sample_bronze_issues)

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    cleaner.process_repository("test_owner", "test_repo")

    processed_file = tmp_path / "processed" / "github" / "test_owner" / "test_repo" / "issues.json"
    with open(processed_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    assert records[0]["created_at"] == "2026-01-10T08:00:00+00:00"
    assert records[0]["closed_at"] == "2026-01-11T09:00:00+00:00"


def test_pull_request_reference_extraction(tmp_path, sample_bronze_issues):
    """8. Test pull request reference extraction."""
    setup_bronze_dir(tmp_path, "test_owner", "test_repo", sample_bronze_issues)

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    cleaner.process_repository("test_owner", "test_repo")

    processed_file = tmp_path / "processed" / "github" / "test_owner" / "test_repo" / "issues.json"
    with open(processed_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    prs = records[0]["linked_pull_requests"]
    assert len(prs) == 1
    assert prs[0]["pr_number"] == 43
    assert prs[0]["html_url"] == "https://github.com/test_owner/test_repo/pull/43"


def test_explicit_duplicate_detection(tmp_path, sample_bronze_issues):
    """9. Test explicit duplicate pattern detection."""
    setup_bronze_dir(tmp_path, "test_owner", "test_repo", sample_bronze_issues)

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    cleaner.process_repository("test_owner", "test_repo")

    processed_file = tmp_path / "processed" / "github" / "test_owner" / "test_repo" / "issues.json"
    with open(processed_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    record_42 = records[0]
    assert record_42["duplicate_detected"] is True
    assert record_42["duplicate_of_issue_number"] == 100


def test_non_duplicate_issue_references(tmp_path, sample_bronze_issues):
    """10. Test that non-duplicate issue numbers mentioned in text do NOT trigger duplicate detection."""
    setup_bronze_dir(tmp_path, "test_owner", "test_repo", sample_bronze_issues)

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    cleaner.process_repository("test_owner", "test_repo")

    processed_file = tmp_path / "processed" / "github" / "test_owner" / "test_repo" / "issues.json"
    with open(processed_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    record_50 = records[2]
    assert record_50["duplicate_detected"] is False
    assert record_50["duplicate_of_issue_number"] is None


def test_invalid_issue_record_handling(tmp_path):
    """11. Test malformed/invalid issue record handling without crashing."""
    bad_issues = [
        {"id": -5, "number": -1, "title": "Invalid negative ID"},  # Validation error
        {"id": 200, "number": 10, "title": "Valid issue", "user": None, "created_at": "2026-01-01T00:00:00Z"}
    ]
    setup_bronze_dir(tmp_path, "test_owner", "test_repo", bad_issues)

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    report = cleaner.process_repository("test_owner", "test_repo")

    assert report["total_raw_issues"] == 2
    assert report["valid_issues"] == 1
    assert report["invalid_issues"] == 1


def test_deterministic_output(tmp_path, sample_bronze_issues):
    """12. Test running processor twice produces identical output."""
    setup_bronze_dir(tmp_path, "test_owner", "test_repo", sample_bronze_issues)

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    
    # Run 1
    cleaner.process_repository("test_owner", "test_repo")
    processed_file = tmp_path / "processed" / "github" / "test_owner" / "test_repo" / "issues.json"
    with open(processed_file, "r", encoding="utf-8") as f:
        run1_data = json.load(f)

    # Run 2
    cleaner.process_repository("test_owner", "test_repo")
    with open(processed_file, "r", encoding="utf-8") as f:
        run2_data = json.load(f)

    assert run1_data == run2_data


def test_empty_dataset_handling(tmp_path):
    """13. Test empty Bronze issue dataset."""
    setup_bronze_dir(tmp_path, "test_owner", "test_repo", [])

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    report = cleaner.process_repository("test_owner", "test_repo")

    assert report["total_raw_issues"] == 0
    assert report["valid_issues"] == 0
    assert report["invalid_issues"] == 0


def test_multiple_repositories_handling(tmp_path, sample_bronze_issues):
    """14. Test handling multiple distinct repositories independently."""
    setup_bronze_dir(tmp_path, "org_a", "repo_a", sample_bronze_issues[:1])
    setup_bronze_dir(tmp_path, "org_b", "repo_b", sample_bronze_issues[1:])

    cleaner = IssueCleaner(raw_data_dir=str(tmp_path / "raw"), processed_data_dir=str(tmp_path / "processed"))
    
    report_a = cleaner.process_repository("org_a", "repo_a")
    report_b = cleaner.process_repository("org_b", "repo_b")

    assert report_a["repository"] == "org_a/repo_a"
    assert report_a["valid_issues"] == 1

    assert report_b["repository"] == "org_b/repo_b"
    assert report_b["valid_issues"] == 2
