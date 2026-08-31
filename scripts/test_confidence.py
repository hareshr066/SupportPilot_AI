import sys
import logging
import argparse
from pathlib import Path

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.session import get_db
from app.database.models import Issue, ResolutionRun
from app.services.claim_verification_service import ClaimVerificationService
from app.services.confidence_service import (
    ConfidenceCalibrationService,
    extract_confidence_features,
    render_human_readable_confidence,
)
from sqlalchemy import select

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("test_confidence")


def main():
    parser = argparse.ArgumentParser(
        description="SupportPilot - End-to-End Calibrated Confidence & Decision CLI"
    )
    parser.add_argument("--issue-id", type=int, default=None, help="Issue DB ID to test confidence for")
    parser.add_argument("--latest", action="store_true", help="Test latest issue and resolution run")

    args = parser.parse_args()

    with get_db() as session:
        target_issue_id = args.issue_id

        if args.latest or not target_issue_id:
            latest_run = session.scalar(
                select(ResolutionRun).order_by(ResolutionRun.id.desc()).limit(1)
            )
            if not latest_run:
                logger.error("No ResolutionRun records found in database. Run resolution generation first.")
                sys.exit(1)
            target_issue_id = latest_run.issue_id
            target_res_run = latest_run
        else:
            target_res_run = session.scalar(
                select(ResolutionRun).where(ResolutionRun.issue_id == target_issue_id).order_by(ResolutionRun.id.desc()).limit(1)
            )

        if not target_res_run:
            logger.error(f"No ResolutionRun found for issue_id {target_issue_id}.")
            sys.exit(1)

        issue_rec = session.scalar(select(Issue).where(Issue.id == target_issue_id))
        issue_title = issue_rec.title if issue_rec else "Unknown Issue"

        # 1. Independent Claim Verification
        ver_service = ClaimVerificationService(db_session=session)
        ver_summary = ver_service.verify_resolution(resolution_run_id=target_res_run.run_id, session=session)

        # 2. Extract Confidence Features
        res_data = target_res_run.raw_output or {}
        ret_meta = {
            "top_dense_similarity": 0.82,
            "top_bm25_score": 14.5,
            "top_rrf_score": 0.032,
            "retrieval_score_gap": 0.08,
            "evidence_completeness": 0.75,
            "num_retrieved_cases": 5,
            "num_usable_sources": 4
        }
        features = extract_confidence_features(
            resolution_run_data=res_data,
            verification_summary=ver_summary,
            retrieval_metadata=ret_meta
        )

        # 3. Calibrated Confidence Prediction & Decision
        conf_service = ConfidenceCalibrationService()
        pred = conf_service.compute_confidence_and_decision(
            features=features,
            verification_summary=ver_summary,
            ticket_id=target_issue_id,
            resolution_run_id=target_res_run.run_id,
            session=session
        )

        # Render Human Readable Report
        report = render_human_readable_confidence(pred)
        print(f"TICKET TITLE: {issue_title}")
        print(report)


if __name__ == "__main__":
    main()
