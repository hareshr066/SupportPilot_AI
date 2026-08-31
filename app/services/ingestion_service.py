import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from config import settings
from app.services.github_client import GitHubClient

logger = logging.getLogger(__name__)

class IngestionService:
    """
    Bronze Data Ingestion Service.
    
    Responsible solely for fetching raw repository issue data via GitHubClient
    and persisting it unmodified into the Bronze raw storage layer.
    
    Does NOT clean, transform, normalize, filter fields, generate embeddings,
    or write to a database.
    """

    def __init__(self, client: Optional[GitHubClient] = None, raw_data_dir: Optional[str] = None):
        """
        Initializes the IngestionService with a GitHubClient and storage path.

        Args:
            client: Optional GitHubClient instance. Default instance created if omitted.
            raw_data_dir: Optional path override for raw storage directory.
        """
        self.client = client or GitHubClient()
        self.raw_data_dir = Path(raw_data_dir or settings.raw_data_dir)

    def ingest_repository(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        max_issues: Optional[int] = None,
        fetch_comments: bool = True,
        max_comments_per_issue: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Ingests raw GitHub issues and their comments for a repository and persists them locally.

        Target Storage Structure:
            <raw_data_dir>/github/<owner>/<repo>/
                ├── issues.json
                ├── comments.json
                └── metadata.json

        Args:
            owner: The repository owner (username or organization).
            repo: The repository name.
            state: Issue state filter ('open', 'closed', 'all').
            max_issues: Optional maximum number of issues to fetch.
            fetch_comments: Whether to fetch comments for issues with comments_count > 0.
            max_comments_per_issue: Optional max comments to fetch per issue.

        Returns:
            Dict containing ingestion execution metadata.
        """
        repository_name = f"{owner}/{repo}"
        logger.info(f"Starting raw issue ingestion for repository: {repository_name} (state={state})")

        # 1. Fetch raw unmodified issues from GitHub API
        raw_issues = self.client.fetch_repository_issues(
            owner=owner,
            repo=repo,
            state=state,
            max_issues=max_issues
        )

        # 2. Fetch raw comments for issues if enabled
        total_comments_fetched = 0
        comments_by_issue: Dict[str, List[Dict[str, Any]]] = {}

        if fetch_comments:
            max_cmts_limit = max_comments_per_issue or getattr(settings, "github_max_comments_per_issue", 50)
            logger.info(f"Fetching comments for {len(raw_issues)} issues (Max comments/issue: {max_cmts_limit})...")
            
            for issue in raw_issues:
                issue_num = issue.get("number")
                comments_count = issue.get("comments", 0)
                if isinstance(comments_count, int) and comments_count > 0 and issue_num:
                    try:
                        raw_cmts = self.client.fetch_issue_comments(
                            owner=owner,
                            repo=repo,
                            issue_number=int(issue_num),
                            max_comments=max_cmts_limit
                        )
                        issue["comments_data"] = raw_cmts
                        comments_by_issue[str(issue_num)] = raw_cmts
                        total_comments_fetched += len(raw_cmts)
                    except Exception as c_exc:
                        logger.warning(f"Failed to fetch comments for issue #{issue_num}: {c_exc}")

        # 3. Prepare target directory
        target_dir = self.raw_data_dir / "github" / owner / repo
        target_dir.mkdir(parents=True, exist_ok=True)

        issues_path = target_dir / "issues.json"
        comments_path = target_dir / "comments.json"
        metadata_path = target_dir / "metadata.json"

        # 4. Build ingestion metadata record
        metadata: Dict[str, Any] = {
            "owner": owner,
            "repository": repo,
            "repository_full_name": repository_name,
            "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
            "issues_count": len(raw_issues),
            "comments_count": total_comments_fetched,
            "source": "GitHub REST API",
            "api_endpoint": f"{self.client.base_url}/repos/{owner}/{repo}/issues",
            "state_filter": state,
            "ingestion_status": "SUCCESS"
        }

        # 5. Write data atomically using temporary files to guarantee idempotency
        temp_issues_path = target_dir / "issues.json.tmp"
        temp_comments_path = target_dir / "comments.json.tmp"
        temp_metadata_path = target_dir / "metadata.json.tmp"

        try:
            with open(temp_issues_path, "w", encoding="utf-8") as f:
                json.dump(raw_issues, f, indent=2, ensure_ascii=False)

            with open(temp_comments_path, "w", encoding="utf-8") as f:
                json.dump(comments_by_issue, f, indent=2, ensure_ascii=False)

            with open(temp_metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            # Atomically replace files
            temp_issues_path.replace(issues_path)
            temp_comments_path.replace(comments_path)
            temp_metadata_path.replace(metadata_path)

            logger.info(
                f"Ingestion completed for {repository_name}. "
                f"Persisted {len(raw_issues)} raw issues and {total_comments_fetched} comments."
            )
            return metadata

        except Exception as exc:
            logger.error(f"Failed to persist raw data for {repository_name}: {exc}")
            for p in [temp_issues_path, temp_comments_path, temp_metadata_path]:
                if p.exists():
                    p.unlink()
            raise exc
