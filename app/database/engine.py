import logging
from typing import Optional
from sqlalchemy import create_engine, Engine, text
from config import settings

logger = logging.getLogger(__name__)

def get_engine(db_url: Optional[str] = None) -> Engine:
    """
    Creates and returns a SQLAlchemy 2.x Engine instance.
    """
    target_url = db_url or settings.database_url
    logger.debug(f"Initializing database engine for target URL dialect: {target_url.split('://')[0]}")
    
    # Configure pooling and echo options
    connect_args = {}
    if target_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    elif target_url.startswith("postgresql"):
        connect_args["connect_timeout"] = 5

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
        logger.warning(f"Database connection to '{target_url.split('@')[-1]}' failed ({exc}). Falling back to local SQLite database.")
        sqlite_url = "sqlite:///./data/support_triage.db"
        return create_engine(
            sqlite_url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
            echo=False
        )

# Global engine instance
engine = get_engine()
