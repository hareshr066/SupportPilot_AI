"""
GitHub Client Module (src.ingestion re-export)

Delegates to the primary GitHubClient implementation in app.services.github_client
to prevent duplication and maintain architectural consistency across the repository.
"""

from app.services.github_client import GitHubClient as GitHubAPIClient, GitHubClient

__all__ = ["GitHubAPIClient", "GitHubClient"]
