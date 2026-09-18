import logging
from typing import Optional
from sqlalchemy import create_engine, Engine, text
from config import settings

logger = logging.getLogger(__name__)

def get_engine(db_url: Optional[str] = None) -> Engine:
    """
    Creates and returns a SQLAlchemy 2.x Engine instance.
    
    Enforces strict environment-aware behavior:
    - In production (APP_ENV=production): Requires a valid, reachable PostgreSQL DATABASE_URL.
      Fails fast with a RuntimeError if missing, invalid, or unreachable. No silent fallback.
    - In development/test: Tries the configured DATABASE_URL. If unreachable and not in production,
      gracefully falls back to local SQLite database with an explicit warning log.
    """
    target_url = db_url or settings.database_url
    is_production = getattr(settings, "app_env", "development").lower() in ["production", "prod"]

    if not target_url or not target_url.strip():
        if is_production:
            raise RuntimeError(
                "CRITICAL CONFIGURATION ERROR: DATABASE_URL must be explicitly configured in production mode. "
                "Silent fallback to SQLite is strictly forbidden in production."
            )
        target_url = "sqlite:///./data/support_triage.db"

    # In production mode, SQLite is forbidden
    if is_production and target_url.startswith("sqlite"):
        raise RuntimeError(
            f"CRITICAL CONFIGURATION ERROR: Production environment ('APP_ENV={settings.app_env}') "
            f"cannot use SQLite ('{target_url}'). A production-grade PostgreSQL database URL is required."
        )

    logger.debug(f"Initializing database engine for target URL dialect: {target_url.split('://')[0]}")
    
    # Configure pooling and dialect-specific options
    connect_args = {}
    if target_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    try:
        engine_inst = create_engine(
            target_url,
            pool_pre_ping=True,
            connect_args=connect_args,
            echo=False
        )
        # Test connection ping
        with engine_inst.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine_inst
    except Exception as exc:
        if is_production:
            raise RuntimeError(
                f"CRITICAL DATABASE ERROR: Failed to connect to production database '{target_url.split('@')[-1]}': {exc}. "
                "Aborting startup to prevent ungrounded or silent degraded state."
            ) from exc

        logger.warning(
            f"Database connection to '{target_url.split('@')[-1]}' failed ({exc}). "
            f"Environment '{settings.app_env}' allows fallback to local SQLite database."
        )
        sqlite_url = "sqlite:///./data/support_triage.db"
        return create_engine(
            sqlite_url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
            echo=False
        )

# Global engine instance
engine = get_engine()
