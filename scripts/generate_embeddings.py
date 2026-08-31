import sys
import logging
import argparse
from pathlib import Path
from sqlalchemy import select

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.session import get_db
from app.database.models import Repository
from app.services.embedding_service import EmbeddingService

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("generate_embeddings")


def main() -> None:
    parser = argparse.ArgumentParser(description="SupportPilot - Generate Issue Embeddings")
    parser.add_argument("--owner", type=str, default="microsoft", help="GitHub repository owner (default: microsoft)")
    parser.add_argument("--repo", type=str, default="vscode", help="GitHub repository name (default: vscode)")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size for embedding generation (default: 32)")
    parser.add_argument("--force", action="store_true", help="Re-generate embeddings even if they already exist")

    args = parser.parse_args()
    repo_name = f"{args.owner}/{args.repo}"

    with get_db() as session:
        repository = session.scalar(
            select(Repository).where(Repository.full_name == repo_name)
        )
        if not repository:
            logger.error(f"Repository {repo_name} not found in database. Run load_database.py first!")
            sys.exit(1)

        repo_id = repository.id

    logger.info(f"Generating issue embeddings for repository {repo_name} (ID={repo_id})...")
    service = EmbeddingService()
    report = service.generate_embeddings_for_repository(
        repository_id=repo_id,
        batch_size=args.batch_size,
        force=args.force
    )

    logger.info("==========================================")
    logger.info("  Embedding Generation Completion Report  ")
    logger.info("==========================================")
    logger.info(f"  Repository:           {repo_name}")
    logger.info(f"  Total Issues:         {report['total_issues']}")
    logger.info(f"  Embedded Issues:      {report['embedded']}")
    logger.info(f"  Skipped Issues:       {report['skipped']}")
    logger.info(f"  Model Name:           {service.model_name}")
    logger.info("==========================================")


if __name__ == "__main__":
    main()
