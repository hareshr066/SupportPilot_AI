import re
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from pydantic import BaseModel, Field, field_validator, ValidationError

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# Pydantic Models for Silver Normalized Schema
# ---------------------------------------------------------

class AuthorModel(BaseModel):
    login: str
    id: Optional[int] = None


class AssigneeModel(BaseModel):
    login: str
    id: Optional[int] = None


class CommentModel(BaseModel):
    id: Optional[int] = None
    author: Optional[AuthorModel] = None
    body: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    html_url: Optional[str] = None


class LinkedPRModel(BaseModel):
    pr_number: Optional[int] = None
    url: Optional[str] = None
    html_url: Optional[str] = None
    repository: Optional[str] = None


class NormalizedIssue(BaseModel):
    github_issue_id: int
    repository: str
    issue_number: int
    title: str
    body: str = ""
    state: str
    state_reason: Optional[str] = None
    author: Optional[AuthorModel] = None
    labels: List[str] = Field(default_factory=list)
    assignees: List[AssigneeModel] = Field(default_factory=list)
    created_at: str
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None
    comments_count: int = 0
    comments: List[CommentModel] = Field(default_factory=list)
    linked_pull_requests: List[LinkedPRModel] = Field(default_factory=list)
    html_url: str
    duplicate_of_issue_number: Optional[int] = None
    duplicate_detected: bool = False

    @field_validator("github_issue_id", "issue_number")
    @classmethod
    def validate_positive_ids(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"ID and issue_number must be positive integers, got {v}")
        return v


# ---------------------------------------------------------
# Silver Layer Issue Cleaner Service
# ---------------------------------------------------------

class IssueCleaner:
    """
    Silver Layer Data Processor.
    
    Transforms Bronze raw GitHub issue JSON files into structured, normalized
    Silver records conforming to NormalizedIssue Pydantic schema.
    
    Does NOT call external GitHub APIs. Operates purely on local Bronze data.
    """

    # Deterministic duplicate reference extraction regexes
    # Matches patterns like "duplicate of #1234", "dupe of #1234", "closing as duplicate of #1234", "duplicate of https://github.com/owner/repo/issues/1234"
    DUPLICATE_REGEX_PATTERNS = [
        re.compile(
            r'(?:duplicate\s+of|duplicates|dupe\s+of|closing\s+as\s+duplicate\s+of|marked\s+as\s+duplicate\s+of)\s+#?(\d+)',
            re.IGNORECASE
        ),
        re.compile(
            r'(?:duplicate\s+of|duplicates|dupe\s+of)\s+https?://github\.com/[^/]+/[^/]+/issues/(\d+)',
            re.IGNORECASE
        )
    ]

    PR_URL_REGEX = re.compile(
        r'https?://github\.com/([^/]+/[^/]+)/pull/(\d+)',
        re.IGNORECASE
    )

    def __init__(
        self,
        raw_data_dir: Optional[str] = None,
        processed_data_dir: Optional[str] = None
    ):
        self.raw_data_dir = Path(raw_data_dir or settings.raw_data_dir)
        self.processed_data_dir = Path(processed_data_dir or settings.processed_data_dir)

    def process_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """
        Reads Bronze issues from raw storage, transforms and validates each record,
        writes Silver normalized JSON to processed storage, and returns a execution report.
        """
        repository_name = f"{owner}/{repo}"
        logger.info(f"Starting Silver layer data processing for repository: {repository_name}")

        # Locate Bronze raw issues file
        bronze_issues_path = self.raw_data_dir / "github" / owner / repo / "issues.json"
        
        # Support fallback legacy paths if nested github structure is not present
        if not bronze_issues_path.exists():
            fallback_path = self.raw_data_dir / owner / repo / "issues.json"
            if fallback_path.exists():
                bronze_issues_path = fallback_path
            else:
                err_msg = f"Bronze dataset not found at {bronze_issues_path}"
                logger.error(err_msg)
                raise FileNotFoundError(err_msg)

        logger.info(f"Loading Bronze raw dataset from: {bronze_issues_path}")
        with open(bronze_issues_path, "r", encoding="utf-8") as f:
            raw_issues = json.load(f)

        if not isinstance(raw_issues, list):
            raise ValueError(f"Invalid Bronze data format in {bronze_issues_path}: expected JSON array.")

        # Load raw comments.json if available
        bronze_comments_map: Dict[str, List[Dict[str, Any]]] = {}
        bronze_comments_path = bronze_issues_path.parent / "comments.json"
        if bronze_comments_path.exists():
            try:
                with open(bronze_comments_path, "r", encoding="utf-8") as f:
                    bronze_comments_map = json.load(f)
                logger.info(f"Loaded Bronze comments dataset from: {bronze_comments_path}")
            except Exception as c_err:
                logger.warning(f"Could not load comments file {bronze_comments_path}: {c_err}")

        normalized_records: List[Dict[str, Any]] = []
        
        # Statistics counters for report
        total_raw = len(raw_issues)
        valid_count = 0
        invalid_count = 0
        with_labels = 0
        closed_count = 0
        with_assignees = 0
        with_comments = 0
        duplicate_detected_count = 0
        with_pr_refs = 0

        for idx, raw_issue in enumerate(raw_issues):
            try:
                issue_num_str = str(raw_issue.get("number") or "")
                c_override = bronze_comments_map.get(issue_num_str)
                norm_dict = self._transform_single_issue(raw_issue, repository_name, comments_override=c_override)
                # Validate against Pydantic schema
                validated_model = NormalizedIssue.model_validate(norm_dict)
                record_dict = validated_model.model_dump()
                normalized_records.append(record_dict)

                valid_count += 1
                if record_dict["labels"]:
                    with_labels += 1
                if record_dict["state"] == "closed":
                    closed_count += 1
                if record_dict["assignees"]:
                    with_assignees += 1
                if record_dict["comments_count"] > 0 or record_dict["comments"]:
                    with_comments += 1
                if record_dict["duplicate_detected"]:
                    duplicate_detected_count += 1
                if record_dict["linked_pull_requests"]:
                    with_pr_refs += 1

            except (ValidationError, ValueError, TypeError) as exc:
                invalid_count += 1
                issue_id = raw_issue.get("id") or raw_issue.get("number") or f"index_{idx}"
                logger.warning(
                    f"Validation failed for issue record {issue_id} in {repository_name}: {exc}"
                )

        # Build processing report
        report: Dict[str, Any] = {
            "repository": repository_name,
            "total_raw_issues": total_raw,
            "valid_issues": valid_count,
            "invalid_issues": invalid_count,
            "issues_with_labels": with_labels,
            "closed_issues": closed_count,
            "issues_with_assignees": with_assignees,
            "issues_with_comments": with_comments,
            "detected_duplicates_count": duplicate_detected_count,
            "issues_with_pr_references": with_pr_refs,
            "processing_timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Persist normalized records and processing report atomically
        target_dir = self.processed_data_dir / "github" / owner / repo
        target_dir.mkdir(parents=True, exist_ok=True)

        output_issues_path = target_dir / "issues.json"
        output_report_path = target_dir / "report.json"

        temp_issues_path = target_dir / "issues.json.tmp"
        temp_report_path = target_dir / "report.json.tmp"

        try:
            with open(temp_issues_path, "w", encoding="utf-8") as f:
                json.dump(normalized_records, f, indent=2, ensure_ascii=False)

            with open(temp_report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            temp_issues_path.replace(output_issues_path)
            temp_report_path.replace(output_report_path)

            logger.info(
                f"Silver data processing complete for {repository_name}. "
                f"Successfully saved {valid_count}/{total_raw} valid records to {output_issues_path}."
            )
            return report

        except Exception as exc:
            logger.error(f"Failed to persist Silver dataset for {repository_name}: {exc}")
            if temp_issues_path.exists():
                temp_issues_path.unlink()
            if temp_report_path.exists():
                temp_report_path.unlink()
            raise exc

    def _transform_single_issue(
        self,
        raw: Dict[str, Any],
        repository_name: str,
        comments_override: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Extracts, normalizes, and validates all fields from a raw GitHub issue object.
        """
        # 1. github_issue_id & issue_number
        raw_id = raw.get("id")
        raw_number = raw.get("number")

        github_issue_id = int(raw_id) if raw_id is not None else 0
        issue_number = int(raw_number) if raw_number is not None else 0

        # 2. Title & Body (Preserve original text, handle missing body as empty string)
        title = raw.get("title") or ""
        body_val = raw.get("body")
        body = body_val if isinstance(body_val, str) else ""

        # 3. State & State Reason
        state = raw.get("state") or "open"
        state_reason = raw.get("state_reason")
        if state_reason is not None:
            state_reason = str(state_reason)

        # 4. Author Normalization
        author: Optional[Dict[str, Any]] = None
        user_raw = raw.get("user")
        if isinstance(user_raw, dict) and "login" in user_raw:
            author = {
                "login": str(user_raw["login"]),
                "id": int(user_raw["id"]) if "id" in user_raw and user_raw["id"] is not None else None
            }

        # 5. Label Normalization (Extract list of label name strings)
        labels: List[str] = []
        raw_labels = raw.get("labels", [])
        if isinstance(raw_labels, list):
            for item in raw_labels:
                if isinstance(item, dict) and "name" in item and item["name"]:
                    labels.append(str(item["name"]))
                elif isinstance(item, str) and item:
                    labels.append(item)

        # 6. Assignees Normalization (List of dicts with login & id)
        assignees: List[Dict[str, Any]] = []
        raw_assignees = raw.get("assignees")
        if isinstance(raw_assignees, list) and raw_assignees:
            for item in raw_assignees:
                if isinstance(item, dict) and "login" in item:
                    assignees.append({
                        "login": str(item["login"]),
                        "id": int(item["id"]) if "id" in item and item["id"] is not None else None
                    })
        elif isinstance(raw.get("assignee"), dict):
            single_assignee = raw["assignee"]
            if "login" in single_assignee:
                assignees.append({
                    "login": str(single_assignee["login"]),
                    "id": int(single_assignee["id"]) if "id" in single_assignee and single_assignee["id"] is not None else None
                })

        # 7. Timestamps Normalization
        created_at = self._normalize_timestamp(raw.get("created_at")) or datetime.now(timezone.utc).isoformat()
        updated_at = self._normalize_timestamp(raw.get("updated_at"))
        closed_at = self._normalize_timestamp(raw.get("closed_at"))

        # 8. Comments Normalization
        comments_raw = comments_override if comments_override is not None else raw.get("comments_data", raw.get("comments"))
        comments_count = 0
        comments_list: List[Dict[str, Any]] = []

        if isinstance(raw.get("comments"), int):
            comments_count = raw["comments"]

        if isinstance(comments_raw, list):
            comments_list = [self._normalize_comment(c) for c in comments_raw if isinstance(c, dict)]
            if comments_count == 0 or comments_override is not None:
                comments_count = len(comments_list)

        # 9. Linked Pull Requests Extraction
        linked_prs = self._extract_pull_requests(raw, body, comments_list)

        # 10. Deterministic Duplicate Detection
        dup_num, dup_detected = self._extract_duplicate_relationship(issue_number, body, comments_list)

        # 11. HTML URL
        html_url = str(raw.get("html_url") or f"https://github.com/{repository_name}/issues/{issue_number}")

        return {
            "github_issue_id": github_issue_id,
            "repository": repository_name,
            "issue_number": issue_number,
            "title": title,
            "body": body,
            "state": state,
            "state_reason": state_reason,
            "author": author,
            "labels": labels,
            "assignees": assignees,
            "created_at": created_at,
            "updated_at": updated_at,
            "closed_at": closed_at,
            "comments_count": comments_count,
            "comments": comments_list,
            "linked_pull_requests": linked_prs,
            "html_url": html_url,
            "duplicate_of_issue_number": dup_num,
            "duplicate_detected": dup_detected
        }

    def _normalize_comment(self, comment_raw: Dict[str, Any]) -> Dict[str, Any]:
        c_id = int(comment_raw["id"]) if "id" in comment_raw and comment_raw["id"] is not None else None
        c_body = comment_raw.get("body") or ""
        
        c_author: Optional[Dict[str, Any]] = None
        user_info = comment_raw.get("user")
        if isinstance(user_info, dict) and "login" in user_info:
            c_author = {
                "login": str(user_info["login"]),
                "id": int(user_info["id"]) if "id" in user_info and user_info["id"] is not None else None
            }
        elif isinstance(comment_raw.get("author"), str):
            c_author = {"login": comment_raw["author"]}

        return {
            "id": c_id,
            "author": c_author,
            "body": c_body,
            "created_at": self._normalize_timestamp(comment_raw.get("created_at")),
            "updated_at": self._normalize_timestamp(comment_raw.get("updated_at")),
            "html_url": comment_raw.get("html_url")
        }

    def _extract_pull_requests(
        self,
        raw: Dict[str, Any],
        body: str,
        comments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        linked_prs: List[Dict[str, Any]] = []
        seen_urls: Set[str] = set()

        # Check raw pull_request object
        pr_obj = raw.get("pull_request")
        if isinstance(pr_obj, dict):
            pr_url = pr_obj.get("url") or pr_obj.get("html_url")
            pr_html_url = pr_obj.get("html_url") or pr_url
            
            pr_num = None
            if pr_html_url:
                match = re.search(r'/pull/(\d+)', pr_html_url)
                if match:
                    pr_num = int(match.group(1))

            if pr_html_url and pr_html_url not in seen_urls:
                seen_urls.add(pr_html_url)
                linked_prs.append({
                    "pr_number": pr_num,
                    "url": pr_url,
                    "html_url": pr_html_url,
                    "repository": None
                })

        # Scan body for pull request URLs
        all_text = body + "\n" + "\n".join(c.get("body", "") for c in comments)
        for repo_match, pr_num_str in self.PR_URL_REGEX.findall(all_text):
            url_found = f"https://github.com/{repo_match}/pull/{pr_num_str}"
            if url_found not in seen_urls:
                seen_urls.add(url_found)
                linked_prs.append({
                    "pr_number": int(pr_num_str),
                    "url": f"https://api.github.com/repos/{repo_match}/pulls/{pr_num_str}",
                    "html_url": url_found,
                    "repository": repo_match
                })

        return linked_prs

    def _extract_duplicate_relationship(
        self,
        issue_number: int,
        body: str,
        comments: List[Dict[str, Any]]
    ) -> Tuple[Optional[int], bool]:
        """
        Deterministic pattern matching for explicit duplicate relationships.
        Searches issue body and comment text for explicit duplicate indicators.
        
        Returns:
            Tuple[Optional[int], bool]: (duplicate_of_issue_number, duplicate_detected)
        """
        all_text_sources = [body] + [c.get("body", "") for c in comments]
        candidate_issues: Set[int] = set()

        for text in all_text_sources:
            if not text:
                continue
            for pattern in self.DUPLICATE_REGEX_PATTERNS:
                for match in pattern.finditer(text):
                    ref_num = int(match.group(1))
                    # Avoid self-reference
                    if ref_num != issue_number and ref_num > 0:
                        candidate_issues.add(ref_num)

        # If exactly one confident duplicate candidate issue number was found
        if len(candidate_issues) == 1:
            dup_num = next(iter(candidate_issues))
            return dup_num, True

        # If multiple ambiguous candidates or zero candidates were found
        return None, False

    def _normalize_timestamp(self, timestamp_str: Any) -> Optional[str]:
        if not timestamp_str or not isinstance(timestamp_str, str):
            return None
        try:
            clean_str = timestamp_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception as e:
            logger.warning(f"Timestamp normalization failed for '{timestamp_str}': {e}")
            return None
