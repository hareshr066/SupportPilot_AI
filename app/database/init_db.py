import logging
from sqlalchemy import Engine, text
from app.database.engine import engine as default_engine
from app.database.models import Base
import app.database.models as models_module

logger = logging.getLogger(__name__)

def init_db(engine: Engine = default_engine) -> None:
    """
    Initializes database tables defined in SQLAlchemy ORM models.
    Tests pgvector extension availability and reports status.
    """
    logger.info("Initializing database tables...")
    
    # Test pgvector extension availability on PostgreSQL
    if engine.dialect.name == "postgresql":
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                conn.commit()
            models_module.HAS_PGVECTOR = True
            logger.info("PostgreSQL pgvector extension enabled successfully.")
        except Exception as e:
            models_module.HAS_PGVECTOR = False
            logger.warning(
                f"[ENVIRONMENT LIMITATION REPORT] PostgreSQL pgvector extension is not compiled/available "
                f"on host system: {e}. Falling back to JSON array storage for issue_embeddings table."
            )

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized successfully.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
