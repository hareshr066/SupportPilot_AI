import sys
import logging
import argparse
from typing import Optional

from config import settings
from app.services.issue_cleaner import IssueCleaner

# Configure logging for processing entry point
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("run_processing")

def run_processing(owner: str = "microsoft", repo: str = "vscode") -> None:
    """
    Silver Layer Data Processing Execution Workflow.

    Args:
        owner: GitHub repository owner/organization name.
        repo: GitHub repository name.
    """
    logger.info("Initializing Silver Layer Data Processing Pipeline...")
    logger.info(f"Target repository: {owner}/{repo}")
    logger.info(f"Raw input directory: {settings.raw_data_dir}")
    logger.info(f"Processed output directory: {settings.processed_data_dir}")

    try:
        cleaner = IssueCleaner()
        report = cleaner.process_repository(owner=owner, repo=repo)

        logger.info("Silver data processing completed successfully!")
        logger.info("Processing Report Summary:")
        logger.info(f"  - Total Raw Issues: {report.get('total_raw_issues')}")
        logger.info(f"  - Valid Issues: {report.get('valid_issues')}")
        logger.info(f"  - Invalid Issues: {report.get('invalid_issues')}")
        logger.info(f"  - Closed Issues: {report.get('closed_issues')}")
        logger.info(f"  - Issues with Labels: {report.get('issues_with_labels')}")
        logger.info(f"  - Issues with Assignees: {report.get('issues_with_assignees')}")
        logger.info(f"  - Issues with Comments: {report.get('issues_with_comments')}")
        logger.info(f"  - Detected Duplicates: {report.get('detected_duplicates_count')}")
        logger.info(f"  - Issues with Linked PRs: {report.get('issues_with_pr_references')}")

    except Exception as exc:
        logger.error(f"Silver processing failed fatally: {exc}", exc_info=True)
        sys.exit(1)

def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous Support Triage - Silver Data Processing")
    parser.add_argument("--owner", type=str, default="microsoft", help="GitHub repository owner (default: microsoft)")
    parser.add_argument("--repo", type=str, default="vscode", help="GitHub repository name (default: vscode)")
    
    args = parser.parse_args()
    run_processing(owner=args.owner, repo=args.repo)

if __name__ == "__main__":
    main()
