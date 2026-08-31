import sys
import logging
import argparse
from pathlib import Path

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.session import get_db
from app.database.models import Repository, Issue
from app.services.hybrid_retrieval_service import HybridRetrievalService
from sqlalchemy import select

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("test_retrieval")


def main():
    parser = argparse.ArgumentParser(
        description="SupportPilot - Test Hybrid Resolution-Relevant Retrieval"
    )
    parser.add_argument("--owner", type=str, default="microsoft", help="Repository owner")
    parser.add_argument("--repo", type=str, default="vscode", help="Repository name")
    parser.add_argument("--query", type=str, default=None, help="Raw query text to search for")
    parser.add_argument("--issue-id", type=int, default=None, help="Database issue ID to search for")
    parser.add_argument("--top-k", type=int, default=10, help="Top K resolved cases to retrieve")

    args = parser.parse_args()

    full_name = f"{args.owner}/{args.repo}"
    logger.info(f"Querying Hybrid Retrieval for repository: {full_name}")

    with get_db() as session:
        repo = session.scalar(
            select(Repository).where(Repository.full_name == full_name)
        )
        repo_id = repo.id if repo else None

        query_text = args.query
        query_issue_id = args.issue_id

        if not query_text and query_issue_id:
            iss = session.get(Issue, query_issue_id)
            if iss:
                query_text = f"{iss.title}\n{iss.body}"
            else:
                logger.error(f"Issue ID {query_issue_id} not found in database.")
                sys.exit(1)

        if not query_text:
            query_text = "Terminal window crashes with ERR_CONNECTION_RESET on bash startup"
            logger.info(f"No query text supplied. Using sample query: '{query_text}'")

        service = HybridRetrievalService(db_session=session)
        service.load_or_build_bm25_index(session, repository_id=repo_id)

        results = service.retrieve_resolved_cases(
            query_text=query_text,
            repository_id=repo_id,
            query_issue_id=query_issue_id,
            top_k=args.top_k,
            db_session=session
        )

        print("\n====================================================================================================")
        print(f"                                HYBRID RETRIEVAL RESULTS (Top {len(results)})")
        print("====================================================================================================")
        print(f"{'Rank':<5} | {'Issue #':<8} | {'Final Score':<11} | {'Dense Score':<11} | {'BM25 Score':<11} | {'Evidence':<8} | {'Title'}")
        print("----------------------------------------------------------------------------------------------------")

        for idx, res in enumerate(results, 1):
            title = res['title'][:40] + "..." if len(res['title']) > 40 else res['title']
            print(
                f"{idx:<5} | #{res['issue_number']:<7} | {res['final_score']:<11.6f} | "
                f"{res['dense_score']:<11.4f} | {res['bm25_score']:<11.4f} | {res['evidence_score']:<8.2f} | {title}"
            )

        print("====================================================================================================\n")


if __name__ == "__main__":
    main()
