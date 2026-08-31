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
from app.services.evaluation import DuplicateEvaluationService

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("evaluate_duplicate_detection")


def main() -> None:
    parser = argparse.ArgumentParser(description="SupportPilot - Evaluate Duplicate Detection System")
    parser.add_argument("--owner", type=str, default="microsoft", help="GitHub repository owner (default: microsoft)")
    parser.add_argument("--repo", type=str, default="vscode", help="GitHub repository name (default: vscode)")

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

    logger.info(f"Evaluating duplicate detection system for repository {repo_name}...")
    eval_service = DuplicateEvaluationService()
    metrics = eval_service.evaluate_repository(repository_id=repo_id)

    logger.info("==========================================")
    logger.info("  Duplicate Detection Evaluation Summary  ")
    logger.info("==========================================")
    logger.info(f"  Repository:                       {repo_name}")
    logger.info(f"  Total Ground-Truth Queries:      {metrics.total_eval_queries}")
    logger.info(f"  Valid Pairs Found in Database:    {metrics.ground_truth_pairs_found}")
    logger.info("------------------------------------------")
    logger.info("  Stage 1 Bi-Encoder Retrieval Metrics:")
    logger.info(f"    - Recall@1:                     {metrics.recall_at_1:.4f}")
    logger.info(f"    - Recall@5:                     {metrics.recall_at_5:.4f}")
    logger.info(f"    - Recall@10:                    {metrics.recall_at_10:.4f}")
    logger.info(f"    - Recall@20:                    {metrics.recall_at_20:.4f}")
    logger.info("------------------------------------------")
    logger.info("  Stage 2 Cross-Encoder Threshold Grid:")
    for res in metrics.threshold_grid_results:
        logger.info(
            f"    - Threshold {res['threshold']:.1f} | Precision: {res['precision']:.4f} | "
            f"Recall: {res['recall']:.4f} | F1: {res['f1']:.4f}"
        )
    logger.info("------------------------------------------")
    logger.info(f"  Optimal Validation Threshold:     {metrics.selected_threshold}")
    logger.info("  Final Test Set Evaluation Metrics:")
    logger.info(f"    - Precision:                    {metrics.precision:.4f}")
    logger.info(f"    - Recall:                       {metrics.recall:.4f}")
    logger.info(f"    - F1 Score:                     {metrics.f1_score:.4f}")
    logger.info(f"    - True Positives:               {metrics.true_positives}")
    logger.info(f"    - False Positives:              {metrics.false_positives}")
    logger.info(f"    - False Negatives:              {metrics.false_negatives}")
    logger.info("==========================================")


if __name__ == "__main__":
    main()
