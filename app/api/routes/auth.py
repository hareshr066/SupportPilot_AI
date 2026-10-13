"""
auth.py — Authentication and session routes for SupportPilot multi-tenant dashboard.
"""
from typing import Optional
from datetime import datetime
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from sqlalchemy.orm import Session

from app.database.session import get_db_session
from app.database.models import DashboardUser, Organization
from app.core.auth_service import (
    authenticate_user,
    create_access_token,
    create_dashboard_user,
    get_or_create_organization,
    get_user_by_email,
)
from app.core.auth_middleware import get_current_dashboard_user

router = APIRouter(prefix="", tags=["Authentication"])


# ── Request / Response Schemas ────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="Minimum 6 characters")
    full_name: str = Field(..., min_length=2, max_length=100)
    organization_name: Optional[str] = Field(None, max_length=150)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    api_key: str
    created_at: Optional[datetime] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    org_id: int
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    organization: OrganizationResponse


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db_session)):
    """
    Register a new user and create (or join) an organization.
    Returns access token, user profile, and organization API key.
    """
    clean_email = payload.email.lower().strip()
    existing = get_user_by_email(db, clean_email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists. Please log in.",
        )

    # Determine organization name
    org_name = (
        payload.organization_name.strip()
        if payload.organization_name and payload.organization_name.strip()
        else f"{payload.full_name.strip()}'s Workspace"
    )

    org = get_or_create_organization(db, org_name)
    user = create_dashboard_user(
        db=db,
        email=clean_email,
        password=payload.password,
        full_name=payload.full_name,
        org_id=org.id,
    )

    token = create_access_token(
        user_id=user.id,
        email=user.email,
        org_id=org.id,
        org_name=org.name,
    )

    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse.model_validate(org),
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db_session)):
    """
    Authenticate with email and password to receive a JWT session token.
    """
    user = authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    org = user.organization
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        org_id=org.id if org else 0,
        org_name=org.name if org else "Default",
    )

    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse.model_validate(org) if org else OrganizationResponse(
            id=0, name="Default", api_key=""
        ),
    )


@router.get("/me", response_model=AuthResponse)
def get_me(current_user: DashboardUser = Depends(get_current_dashboard_user)):
    """
    Get current logged in user's profile and organization details.
    """
    org = current_user.organization
    # Re-issue or reflect access token
    token = create_access_token(
        user_id=current_user.id,
        email=current_user.email,
        org_id=org.id if org else 0,
        org_name=org.name if org else "Default",
    )

    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(current_user),
        organization=OrganizationResponse.model_validate(org) if org else OrganizationResponse(
            id=0, name="Default", api_key=""
        ),
    )


@router.post("/rotate-api-key", response_model=OrganizationResponse)
def rotate_org_api_key(
    current_user: DashboardUser = Depends(get_current_dashboard_user),
    db: Session = Depends(get_db_session),
):
    """
    Rotate the organization's server-to-server API key.
    """
    org = current_user.organization
    if not org:
        raise HTTPException(status_code=400, detail="User is not associated with an organization.")

    new_key = f"sp_live_{secrets.token_urlsafe(32)}"
    org.api_key = new_key
    db.commit()
    db.refresh(org)

    return OrganizationResponse.model_validate(org)
