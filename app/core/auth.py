from typing import Optional, Dict, Any
from fastapi import Request, Depends

class UserIdentity:
    """Represents the authenticated caller identity."""
    def __init__(self, user_id: str = "dev_user", role: str = "developer", is_authenticated: bool = True):
        self.user_id = user_id
        self.role = role
        self.is_authenticated = is_authenticated


async def get_current_user(request: Request) -> UserIdentity:
    """
    Clean authentication dependency boundary for FastAPI routes.
    Can be configured/extended for OAuth2, API Keys, or JWT tokens.
    For local development, defaults to an authenticated development identity.
    """
    auth_header = request.headers.get("Authorization")
    api_key_header = request.headers.get("X-API-Key")
    
    # Boundary place-holder for production key/token validation:
    if auth_header or api_key_header:
        user_id = auth_header.replace("Bearer ", "") if auth_header else "api_key_user"
        return UserIdentity(user_id=user_id, role="api_client", is_authenticated=True)
        
    return UserIdentity(user_id="dev_user", role="developer", is_authenticated=True)
