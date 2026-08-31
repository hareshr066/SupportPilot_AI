import sys
import logging
import argparse
from pathlib import Path

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.session import get_db
from app.database.models import Repository
from app.services.hybrid_retrieval_service import HybridRetrievalService
from sqlalchemy import select

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("build_retrieval_index")


def main():
    parser = argparse.ArgumentParser(
        description="SupportPilot - Build Canonical BM25 Retrieval Index"
    )
    parser.add_argument("--owner", type=str, default="microsoft", help="Repository owner (default: microsoft)")
    parser.add_argument("--repo", type=str, default="vscode", help="Repository name (default: vscode)")
    parser.add_argument("--version", type=str, default="v1", help="Index version identifier (default: v1)")

    args = parser.parse_args()

    full_name = f"{args.owner}/{args.repo}"
    logger.info(f"Building retrieval index for repository: {full_name}")

    with get_db() as session:
        repo = session.scalar(
            select(Repository).where(Repository.full_name == full_name)
        )
        repo_id = repo.id if repo else None

        service = HybridRetrievalService(db_session=session)

        try:
            result = service.build_retrieval_index(
                session=session,
                repository_id=repo_id,
                index_version=args.version
            )

            logger.info("==================================================")
            logger.info("  RETRIEVAL INDEX BUILD SUMMARY                   ")
            logger.info("==================================================")
            logger.info(f"  Index Version:     {result['index_version']}")
            logger.info(f"  Document Count:    {result['document_count']}")
            logger.info(f"  Index Saved Path:  {result['index_path']}")
            logger.info(f"  Build Timestamp:   {result['build_timestamp']}")
            logger.info("==================================================")

        except Exception as exc:
            logger.error(f"Index build failed: {exc}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
