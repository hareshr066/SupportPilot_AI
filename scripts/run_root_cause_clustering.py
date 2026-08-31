import sys
import logging
import argparse
from pathlib import Path

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.session import get_db
from app.database.models import Repository
from app.services.root_cause_service import RootCauseService
from sqlalchemy import select

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("run_root_cause_clustering")


def main():
    parser = argparse.ArgumentParser(
        description="SupportPilot - Unsupervised Root-Cause Discovery & Clustering"
    )
    parser.add_argument("--owner", type=str, default="microsoft", help="Repository owner (default: microsoft)")
    parser.add_argument("--repo", type=str, default="vscode", help="Repository name (default: vscode)")
    parser.add_argument("--state", type=str, default=None, help="Issue state filter (default: closed or fallback to all)")
    parser.add_argument("--min-cluster-size", type=int, default=None, help="HDBSCAN min_cluster_size")
    parser.add_argument("--min-samples", type=int, default=None, help="HDBSCAN min_samples")

    args = parser.parse_args()

    full_name = f"{args.owner}/{args.repo}"
    logger.info(f"Starting Root-Cause Discovery Pipeline for repository: {full_name}")

    with get_db() as session:
        repo = session.scalar(
            select(Repository).where(Repository.full_name == full_name)
        )
        if not repo:
            logger.warning(
                f"Repository '{full_name}' not found in database. "
                f"Attempting to query repository_id=1 as default."
            )
            repo_id = 1
        else:
            repo_id = repo.id

        service = RootCauseService(db_session=session)

        try:
            results = service.run_discovery_pipeline(
                repository_id=repo_id,
                db_session=session,
                min_cluster_size=args.min_cluster_size,
                min_samples=args.min_samples,
                state_filter=args.state
            )

            logger.info("==================================================")
            logger.info("  ROOT-CAUSE DISCOVERY PIPELINE EXECUTION SUMMARY  ")
            logger.info("==================================================")
            logger.info(f"  Run ID:                    {results['run_id']}")
            logger.info(f"  Repository ID:             {results['repository_id']}")
            logger.info(f"  Total Closed Issues:       {results['total_closed_issues']}")
            logger.info(f"  Eligible Issues:           {results['eligible_issues']}")
            logger.info(f"  Embedding Model Reused:    {results['embedding_model']}")
            logger.info(f"  Embedding Dimensions:      {results['embedding_dims']}")
            logger.info(f"  Discovered Clusters:       {results['discovered_clusters_count']}")
            logger.info(f"  Noise Count:               {results['noise_count']} ({results['noise_percentage']}%)")
            logger.info(f"  Weighted Cluster Purity:   {results['weighted_purity']}")
            logger.info(f"  Normalized Mut. Info(NMI): {results['nmi']}")
            logger.info(f"  Stability (ARI):           {results['stability_ari']}")
            logger.info(f"  Labeled Clusters Count:    {results['labeled_clusters_count']}")
            logger.info(f"  Runtime (Seconds):         {results['runtime_seconds']}s")
            logger.info(f"  Artifact Directory:        {results['artifact_dir']}")
            logger.info("==================================================")

        except Exception as exc:
            logger.error(f"Root-cause discovery failed: {exc}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
