import time
import random
import logging
from typing import Any, Dict, List, Optional
import requests
from config import settings

logger = logging.getLogger("supportpilot.github_client")


class GitHubClient:
    """
    A production-grade, reusable client for interacting with the GitHub REST API.
    
    Handles authorization, standard request headers, automatic pagination,
    exponential backoff for transient errors, and rate limit throttling.
    Strictly READ-ONLY with respect to GitHub data.
    """

    def __init__(self, token: Optional[str] = None, base_url: str = "https://api.github.com", timeout: float = 10.0):
        """
        Initializes the GitHubClient with a persistent session and authentication.

        Args:
            token: Optional GitHub PAT. Defaults to the token configured in settings.
            base_url: The base URL of the GitHub REST API.
            timeout: HTTP request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        
        # Configure global headers for all session requests
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        
        # Use provided token, fallback to settings token
        auth_token = token or settings.github_token
        if auth_token and auth_token.strip():
            headers["Authorization"] = f"Bearer {auth_token.strip()}"
            logger.info("GitHubClient session configured with Bearer token authentication.")
        else:
            logger.warning("GitHubClient initialized without token. Unauthenticated requests have lower rate limits.")
            
        self.session.headers.update(headers)

    @property
    def is_authenticated(self) -> bool:
        """Returns True if the client is configured with a valid Bearer token."""
        return "Authorization" in self.session.headers

    def get_auth_status_summary(self) -> str:
        """
        Returns a safe human-readable authentication status string without exposing credentials.
        """
        if self.is_authenticated:
            return "Connected (Authenticated)"
        return "GitHub authentication not configured"

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """
        Safely queries GitHub rate limit status without leaking secrets.
        """
        try:
            resp = self._request("GET", f"{self.base_url}/rate_limit", max_retries=1)
            data = resp.json()
            core = data.get("resources", {}).get("core", {})
            return {
                "authenticated": self.is_authenticated,
                "status": self.get_auth_status_summary(),
                "limit": core.get("limit", 60 if not self.is_authenticated else 5000),
                "remaining": core.get("remaining", 0),
                "reset_epoch": core.get("reset", 0),
            }
        except Exception as exc:
            logger.warning(f"Failed to fetch GitHub rate limit: {exc}")
            return {
                "authenticated": self.is_authenticated,
                "status": self.get_auth_status_summary(),
                "error": "Rate limit query failed"
            }

    def _request(
        self,
        method: str,
        url: str,
        max_retries: int = 3,
        base_delay: float = 1.0,
        **kwargs: Any
    ) -> requests.Response:
        """
        Executes an HTTP request with retry logic and exponential backoff.
        """
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout

        for attempt in range(max_retries):
            try:
                response = self.session.request(method, url, **kwargs)
                
                # Check for rate limiting status codes
                is_rate_limit = False
                if response.status_code == 429:
                    is_rate_limit = True
                elif response.status_code == 403:
                    remaining = response.headers.get("X-RateLimit-Remaining")
                    if remaining == "0":
                        is_rate_limit = True
                    else:
                        try:
                            body = response.json()
                            if "rate limit" in body.get("message", "").lower():
                                is_rate_limit = True
                        except Exception:
                            pass
                
                if is_rate_limit:
                    reset_epoch = response.headers.get("X-RateLimit-Reset")
                    if reset_epoch:
                        sleep_duration = max(float(reset_epoch) - time.time() + 1.0, 1.0)
                    else:
                        sleep_duration = 5.0  # Safe short sleep for dev/testing
                    
                    logger.warning(
                        f"GitHub API Rate Limit reached. Sleeping for {sleep_duration:.2f} seconds before retrying..."
                    )
                    time.sleep(sleep_duration)
                    continue
                
                # Check for transient server errors (500, 502, 503, 504)
                if response.status_code in [500, 502, 503, 504]:
                    if attempt == max_retries - 1:
                        logger.error(f"HTTP {response.status_code} received. Exceeded maximum retries ({max_retries}).")
                        response.raise_for_status()
                    
                    sleep_duration = base_delay * (2 ** attempt) + random.uniform(0.0, 0.5)
                    logger.warning(
                        f"Transient HTTP {response.status_code} received on attempt {attempt + 1}. "
                        f"Retrying in {sleep_duration:.2f} seconds..."
                    )
                    time.sleep(sleep_duration)
                    continue
                
                # Do not retry on 401, 403 (non-rate-limit), 404
                response.raise_for_status()
                return response

            except requests.RequestException as exc:
                if attempt == max_retries - 1:
                    logger.error(f"Network request failed after maximum retries: {exc}")
                    raise exc
                
                sleep_duration = base_delay * (2 ** attempt) + random.uniform(0.0, 0.5)
                logger.warning(
                    f"Network error encountered (Attempt {attempt + 1}/{max_retries}): {exc}. "
                    f"Retrying in {sleep_duration:.2f} seconds..."
                )
                time.sleep(sleep_duration)
                
        raise requests.RequestException("Request failed to resolve within retry limits.")

    def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """Fetches metadata for a GitHub repository."""
        url = f"{self.base_url}/repos/{owner}/{repo}"
        logger.info(f"Fetching repository metadata for {owner}/{repo}")
        resp = self._request("GET", url)
        return resp.json()

    def get_issue(self, owner: str, repo: str, issue_number: int) -> Dict[str, Any]:
        """Fetches a single issue by number."""
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}"
        logger.info(f"Fetching issue #{issue_number} for {owner}/{repo}")
        resp = self._request("GET", url)
        return resp.json()

    def get_pull_request(self, owner: str, repo: str, pull_number: int) -> Dict[str, Any]:
        """Fetches details for a linked pull request."""
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}"
        logger.info(f"Fetching pull request #{pull_number} for {owner}/{repo}")
        resp = self._request("GET", url)
        return resp.json()

    def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        since: Optional[str] = None,
        per_page: int = 100,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Lists a single page of issues for a repository.
        Supports filtering by state and incremental sync via `since` (ISO 8601 string).
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/issues"
        params: Dict[str, Any] = {
            "state": state,
            "per_page": per_page,
            "page": page,
            "sort": "updated",
            "direction": "asc"
        }
        if since:
            params["since"] = since

        logger.debug(f"Fetching page {page} of issues for {owner}/{repo} (since={since})")
        resp = self._request("GET", url, params=params)
        data = resp.json()
        return data if isinstance(data, list) else []

    def fetch_repository_issues(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        since: Optional[str] = None,
        max_issues: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches all issues from a given repository using automatic pagination and optional incremental sync.
        """
        issues: List[Dict[str, Any]] = []
        page = 1
        per_page = min(100, max_issues) if max_issues else 100

        logger.info(f"Starting paginated ingestion of issues for {owner}/{repo} (State: {state}, since: {since})")

        while True:
            page_data = self.list_issues(
                owner=owner,
                repo=repo,
                state=state,
                since=since,
                per_page=per_page,
                page=page
            )
            if not page_data:
                break

            issues.extend(page_data)
            logger.info(f"Page {page} fetched: {len(page_data)} items (Total: {len(issues)})")

            if max_issues and len(issues) >= max_issues:
                issues = issues[:max_issues]
                break

            if len(page_data) < per_page:
                break

            page += 1

        return issues

    def fetch_issue_comments(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        max_comments: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches all comments for a specific issue from GitHub API using automatic pagination.
        """
        comments: List[Dict[str, Any]] = []
        page = 1
        per_page = 100
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments"

        while True:
            params = {"per_page": per_page, "page": page}
            resp = self._request("GET", url, params=params)
            page_data = resp.json()

            if not isinstance(page_data, list) or not page_data:
                break

            comments.extend(page_data)

            if max_comments and len(comments) >= max_comments:
                comments = comments[:max_comments]
                break

            if len(page_data) < per_page:
                break

            page += 1

        return comments
