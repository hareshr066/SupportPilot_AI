import logging
from typing import Optional, Dict, Any
from fastapi import Request, Depends, status
from config import settings
from app.core.errors import APIException

logger = logging.getLogger("supportpilot.auth")

class UserIdentity:
    """Represents the authenticated caller identity."""
    def __init__(self, user_id: str = "dev_user", role: str = "developer", is_authenticated: bool = True):
        self.user_id = user_id
        self.role = role
        self.is_authenticated = is_authenticated


async def get_current_user(request: Request) -> UserIdentity:
    """
    Clean authentication dependency boundary for FastAPI routes.
    If SUPPORTPILOT_API_KEY is configured:
      - Validates Authorization: Bearer <key> or X-API-Key: <key>.
      - Rejects invalid or missing keys with HTTP 401 Unauthorized.
    If SUPPORTPILOT_API_KEY is omitted (dev mode):
      - Accepts request with development identity.
    """
    configured_key = settings.supportpilot_api_key
    auth_header = request.headers.get("Authorization")
    api_key_header = request.headers.get("X-API-Key")

    provided_key = None
    if auth_header and auth_header.startswith("Bearer "):
        provided_key = auth_header[7:].strip()
    elif api_key_header:
        provided_key = api_key_header.strip()

    if configured_key and configured_key.strip():
        if not provided_key or provided_key != configured_key.strip():
            raise APIException(
                "UNAUTHORIZED",
                "Invalid or missing API key.",
                status_code=status.HTTP_401_UNAUTHORIZED
            )
        return UserIdentity(user_id="service_account", role="external_service", is_authenticated=True)

    if provided_key:
        return UserIdentity(user_id="api_key_user", role="api_client", is_authenticated=True)

    return UserIdentity(user_id="dev_user", role="developer", is_authenticated=True)

