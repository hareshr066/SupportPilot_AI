import time
import random
import logging
from typing import Any, Dict, List, Optional
import requests
from config import settings

logger = logging.getLogger(__name__)

class GitHubClient:
    """
    A production-grade, reusable client for interacting with the GitHub REST API.
    
    Handles authorization, standard request headers, automatic pagination,
    exponential backoff for transient errors, and rate limit throttling.
    """

    def __init__(self, token: Optional[str] = None, base_url: str = "https://api.github.com"):
        """
        Initializes the GitHubClient with a persistent session and authentication.

        Args:
            token: Optional GitHub PAT. Defaults to the token configured in settings.
            base_url: The base URL of the GitHub REST API.
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        
        # Configure global headers for all session requests
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        
        # Use provided token, fallback to settings token
        auth_token = token or settings.github_token
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
            logger.info("GitHubClient session configured with Bearer token authentication.")
        else:
            logger.warning("GitHubClient initialized without token. Unauthenticated requests have lower rate limits.")
            
        self.session.headers.update(headers)

    def _request(self, method: str, url: str, max_retries: int = 5, base_delay: float = 1.0, **kwargs: Any) -> requests.Response:
        """
        Executes an HTTP request with retry logic and exponential backoff.

        Handles:
        - Transient HTTP status errors (500, 502, 503, 504) via exponential backoff.
        - Network/Connection errors via exponential backoff.
        - GitHub Rate limiting (429 and 403 rate-limit responses) by sleeping until reset.
        - Other errors by raising immediately.
        """
        for attempt in range(max_retries):
            try:
                response = self.session.request(method, url, **kwargs)
                
                # Check for rate limiting status codes
                is_rate_limit = False
                if response.status_code == 429:
                    is_rate_limit = True
                elif response.status_code == 403:
                    # GitHub uses 403 for rate limits. We check the remaining headers or response body.
                    remaining = response.headers.get("X-RateLimit-Remaining")
                    if remaining == "0":
                        is_rate_limit = True
                    else:
                        try:
                            body = response.json()
                            if "rate limit" in body.get("message", "").lower():
                                is_rate_limit = True
                        except ValueError:
                            pass
                
                if is_rate_limit:
                    reset_epoch = response.headers.get("X-RateLimit-Reset")
                    if reset_epoch:
                        sleep_duration = max(float(reset_epoch) - time.time() + 1.0, 1.0)
                    else:
                        sleep_duration = 60.0
                    
                    logger.warning(
                        f"GitHub API Rate Limit reached. Sleeping for {sleep_duration:.2f} seconds before retrying..."
                    )
                    time.sleep(sleep_duration)
                    continue  # Retry after sleeping
                
                # Check for transient server errors (retryable)
                if response.status_code in [500, 502, 503, 504]:
                    if attempt == max_retries - 1:
                        logger.error(f"HTTP {response.status_code} received. Exceeded maximum retries ({max_retries}).")
                        response.raise_for_status()
                    
                    # Exponential backoff with random jitter
                    sleep_duration = base_delay * (2 ** attempt) + random.uniform(0.0, 1.0)
                    logger.warning(
                        f"Transient HTTP {response.status_code} received on attempt {attempt + 1}. "
                        f"Retrying in {sleep_duration:.2f} seconds..."
                    )
                    time.sleep(sleep_duration)
                    continue
                
                # Raise exception for any other non-success status codes (4xx/5xx)
                response.raise_for_status()
                return response

            except requests.RequestException as exc:
                if attempt == max_retries - 1:
                    logger.error(f"Network request failed after maximum retries: {exc}")
                    raise exc
                
                # Exponential backoff with random jitter
                sleep_duration = base_delay * (2 ** attempt) + random.uniform(0.0, 1.0)
                logger.warning(
                    f"Network error encountered (Attempt {attempt + 1}/{max_retries}): {exc}. "
                    f"Retrying in {sleep_duration:.2f} seconds..."
                )
                time.sleep(sleep_duration)
                
        # Fallback raised if loop completes without returning
        raise requests.RequestException("Request failed to resolve within retry limits.")

    def fetch_repository_issues(self, owner: str, repo: str, state: str = "open") -> List[Dict[str, Any]]:
        """
        Fetches all issues from a given GitHub repository using automatic pagination.

        Note:
            This returns raw issues in their unmodified format. The GitHub API returns 
            both standard issues and pull requests via this endpoint; we do not filter 
            or transform these objects here to preserve the raw schema.

        Args:
            owner: The owner of the repository (e.g. org or username).
            repo: The name of the repository.
            state: Filter issues by state. Can be 'open', 'closed', or 'all'.

        Returns:
            A list of raw dictionary objects representing the repository issues.
        """
        issues: List[Dict[str, Any]] = []
        page = 1
        per_page = 100
        url = f"{self.base_url}/repos/{owner}/{repo}/issues"
        
        logger.info(f"Starting paginated ingestion of issues for {owner}/{repo} (State: {state})")
        
        while True:
            params = {
                "state": state,
                "per_page": per_page,
                "page": page
            }
            
            logger.debug(f"Fetching page {page} for repository {owner}/{repo}...")
            response = self._request("GET", url, params=params)
            
            page_data = response.json()
            if not isinstance(page_data, list):
                logger.error(f"Unexpected API response payload structure (expected list): {page_data}")
                break
                
            if not page_data:
                logger.info(f"Finished fetching all pages of issues. Collected {len(issues)} items.")
                break
                
            issues.extend(page_data)
            logger.info(f"Page {page} successfully fetched. Collected {len(page_data)} items (Total: {len(issues)})")
            
            # If we received fewer items than requested per page, we've reached the end
            if len(page_data) < per_page:
                logger.info("Reached end of available pages.")
                break
                
            page += 1
            
        return issues
