import os
import json
import time
import requests
from typing import List, Dict, Any, Optional
from src.utils.logger import setup_logger

logger = setup_logger("github_client")

class GitHubAPIClient:
    """
    Production-grade GitHub REST API client designed for ticket ingestion.
    Handles rate-limiting auto-backoff, pagination, and raw data persistence.
    """
    BASE_URL = "https://api.github.com"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.session = requests.Session()
        
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            logger.info("GitHubAPIClient initialized with Bearer authentication.")
        else:
            logger.warning("No GitHub token provided. Running in unauthenticated mode (strict rate limit: 60 req/hr).")
            
        self.session.headers.update(headers)

    def _check_rate_limit(self, response: requests.Response) -> None:
        """Inspects rate limit headers and sleeps if threshold reached."""
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset_time = response.headers.get("X-RateLimit-Reset")
        
        if remaining is not None:
            rem_count = int(remaining)
            logger.debug(f"Rate limit remaining: {rem_count}")
            
            if rem_count <= 2:
                sleep_duration = max(0, int(reset_time) - int(time.time())) + 5
                logger.warning(f"Rate limit almost exhausted. Pausing execution for {sleep_duration} seconds...")
                time.sleep(sleep_duration)

    def fetch_repository_issues(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        max_issues: int = 100,
        per_page: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Fetches issues from a given repository using pagination.
        
        Args:
            owner: Repository owner/organization (e.g. 'pallets')
            repo: Repository name (e.g. 'flask')
            state: Issue state ('open', 'closed', 'all')
            max_issues: Total target issue count to retrieve
            per_page: Number of records per API request (max 100)
            
        Returns:
            List of raw issue dictionaries (excluding pull requests).
        """
        issues: List[Dict[str, Any]] = []
        page = 1
        endpoint = f"{self.BASE_URL}/repos/{owner}/{repo}/issues"
        
        logger.info(f"Starting issue ingestion for target repository: {owner}/{repo} (State={state})")
        
        while len(issues) < max_issues:
            params = {
                "state": state,
                "per_page": per_page,
                "page": page,
                "sort": "created",
                "direction": "desc"
            }
            
            try:
                response = self.session.get(endpoint, params=params, timeout=15)
                self._check_rate_limit(response)
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch page {page}. Status Code: {response.status_code}, Body: {response.text}")
                    break
                
                batch = response.json()
                if not batch or not isinstance(batch, list):
                    logger.info("No more issues returned from API. Ending pagination.")
                    break
                
                # Filter out Pull Requests (GitHub issues API returns both Issues and PRs)
                pure_issues = [item for item in batch if "pull_request" not in item]
                issues.extend(pure_issues)
                
                logger.info(f"Page {page}: Fetched {len(batch)} items ({len(pure_issues)} pure issues). Total collected: {len(issues)}")
                
                if len(batch) < params["per_page"]:
                    logger.info("Reached end of available dataset.")
                    break
                
                page += 1
                time.sleep(0.5)  # Respectful API burst throttling
                
            except requests.RequestException as e:
                logger.error(f"Network error on page {page}: {str(e)}")
                break
                
        return issues[:max_issues]

    def save_raw_issues(self, issues: List[Dict[str, Any]], output_path: str) -> None:
        """Persists raw JSON issue objects to disk for auditability and debugging."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(issues, f, indent=2, ensure_ascii=False)
        logger.info(f"Successfully saved {len(issues)} raw issue snapshots to: {output_path}")
