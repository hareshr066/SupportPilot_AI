import sys
import logging
import argparse
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.init_db import init_db
from app.services.database_loader import DatabaseLoader

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("load_database")

def main() -> None:
    parser = argparse.ArgumentParser(description="SupportPilot - Load Silver Dataset to PostgreSQL")
    parser.add_argument("--owner", type=str, default="microsoft", help="GitHub repository owner (default: microsoft)")
    parser.add_argument("--repo", type=str, default="vscode", help="GitHub repository name (default: vscode)")

    args = parser.parse_args()

    logger.info("Initializing PostgreSQL schema...")
    init_db()

    logger.info(f"Loading Silver dataset into PostgreSQL for {args.owner}/{args.repo}...")
    loader = DatabaseLoader()
    report = loader.load_repository(owner=args.owner, repo=args.repo)

    logger.info("Database loading execution report:")
    logger.info(f"  Repository: {report['repository']}")
    logger.info(f"  Total Silver Issues: {report['total_silver_issues']}")
    logger.info(f"  Loaded/Updated Issues: {report['loaded_issues_count']}")
    logger.info(f"  Skipped Issues: {report['skipped_issues_count']}")
    logger.info(f"  Detected Duplicates: {report['duplicate_detected_count']}")

if __name__ == "__main__":
    main()
