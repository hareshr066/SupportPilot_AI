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
from app.services.duplicate_detector import DuplicateDetector

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("test_duplicate_detection")


def main() -> None:
    parser = argparse.ArgumentParser(description="SupportPilot - Run Single Duplicate Detection Query")
    parser.add_argument("--owner", type=str, default="microsoft", help="GitHub repository owner (default: microsoft)")
    parser.add_argument("--repo", type=str, default="vscode", help="GitHub repository name (default: vscode)")
    parser.add_argument("--title", type=str, required=True, help="Issue title text")
    parser.add_argument("--body", type=str, default="", help="Issue description text")
    parser.add_argument("--threshold", type=float, default=None, help="Custom decision threshold (default: config)")

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

    logger.info(f"Running duplicate detection for input issue in {repo_name}...")
    detector = DuplicateDetector(threshold=args.threshold)
    result = detector.detect_duplicate(
        title=args.title,
        body=args.body,
        repository_id=repo_id
    )

    logger.info("==========================================")
    logger.info("    Duplicate Detection Results Summary   ")
    logger.info("==========================================")
    logger.info(f"  Is Duplicate:             {result.is_duplicate}")
    logger.info(f"  Matched Issue ID:         {result.matched_issue_id}")
    logger.info(f"  Matched Issue Number:     {result.matched_issue_number}")
    logger.info(f"  Retrieval Similarity:     {result.retrieval_similarity:.4f}")
    logger.info(f"  Cross-Encoder Score:      {result.cross_encoder_score:.4f}")
    logger.info(f"  Candidates Considered:    {result.candidates_considered}")
    logger.info(f"  Models Used:              {result.model_name}")
    logger.info("==========================================")


if __name__ == "__main__":
    main()
