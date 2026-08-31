import sys
import os
import argparse
import logging

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.evaluation.config import EvaluationConfig
from app.evaluation.runner import MasterEvaluationRunner
from app.database.session import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_evaluation")

def main():
    parser = argparse.ArgumentParser(description="SupportPilot Master Evaluation & Benchmarking CLI")
    parser.add_argument("--repository", type=int, default=None, help="Optional Repository ID to filter dataset")
    parser.add_argument("--split", type=str, default="all", choices=["train", "val", "test", "all"], help="Dataset split to evaluate")
    parser.add_argument(
        "--stage",
        type=str,
        default="all",
        choices=["severity", "duplicate", "root_cause", "retrieval", "resolution", "calibration", "routing", "e2e", "all"],
        help="Pipeline stage to evaluate"
    )
    parser.add_argument("--run-id", type=str, default=None, help="Custom Evaluation Run ID")

    args = parser.parse_args()

    logger.info("Initializing SupportPilot Master Evaluation Engine...")
    config = EvaluationConfig()
    runner = MasterEvaluationRunner(config=config)

    with get_db() as session:
        res = runner.run_evaluation(
            repository_id=args.repository,
            target_stage=args.stage,
            evaluation_run_id=args.run_id,
            db_session=session
        )

    print("\n" + "=" * 60)
    print(f" EVALUATION COMPLETED: {res['evaluation_run_id']}")
    print("=" * 60)
    print(f" Artifacts Directory: {res['artifact_directory']}")
    print("-" * 60)
    print(" SUMMARY METRICS:")
    summary = res["summary"]
    for k, v in summary.items():
        print(f"   {k}: {v}")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
