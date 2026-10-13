"""
auth_service.py — SupportPilot dashboard authentication.

Provides:
  - Password hashing via bcrypt
  - JWT access token generation and validation
  - Dashboard user creation and lookup helpers
"""
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database.models import DashboardUser, Organization

logger = logging.getLogger("supportpilot.auth")

import os
import bcrypt

# Ensure passlib compatibility with bcrypt >= 4.0
if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = type("about", (), {"__version__": getattr(bcrypt, "__version__", "4.0.0")})

# ── crypto config ──────────────────────────────────────────────────────────────
_PWD_CTX = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Secret used to sign JWTs — in production, set JWT_SECRET env var to a 32-byte random value
JWT_SECRET = os.getenv("JWT_SECRET", "supportpilot-jwt-secret-stable-dev-key-change-in-production-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


# ── password helpers ───────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _PWD_CTX.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _PWD_CTX.verify(plain, hashed)


# ── JWT helpers ────────────────────────────────────────────────────────────────

def create_access_token(user_id: int, email: str, org_id: int, org_name: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "org_id": org_id,
        "org_name": org_name,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Returns decoded payload dict or None if invalid/expired."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        logger.debug(f"JWT decode failed: {exc}")
        return None


# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_user_by_email(db: Session, email: str) -> Optional["DashboardUser"]:
    return db.scalar(select(DashboardUser).where(DashboardUser.email == email.lower().strip()))


def get_user_by_id(db: Session, user_id: int) -> Optional["DashboardUser"]:
    return db.scalar(select(DashboardUser).where(DashboardUser.id == user_id))


def get_or_create_organization(db: Session, name: str) -> "Organization":
    """Find an org by name or create it (used during signup)."""
    clean = name.strip()
    org = db.scalar(select(Organization).where(Organization.name == clean))
    if not org:
        api_key = f"sp_live_{secrets.token_urlsafe(32)}"
        org = Organization(
            name=clean,
            api_key=api_key,
            created_at=datetime.now(timezone.utc),
        )
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


def create_dashboard_user(
    db: Session,
    email: str,
    password: str,
    full_name: str,
    org_id: int,
) -> "DashboardUser":
    now = datetime.now(timezone.utc)
    user = DashboardUser(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        org_id=org_id,
        created_at=now,
        last_login_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> Optional["DashboardUser"]:
    """Returns user if credentials are valid, else None."""
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    # Update last_login
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return user
