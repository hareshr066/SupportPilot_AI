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
)
from app.services.routing_service import RoutingEngineService
from app.services.decision_service import (
    DeterministicDecisionEngine,
    render_human_readable_decision,
)
from sqlalchemy import select

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("test_decision")


def main():
    parser = argparse.ArgumentParser(
        description="SupportPilot - End-to-End Routing & Escalation Decision CLI"
    )
    parser.add_argument("--issue-id", type=int, default=None, help="Issue DB ID to test decision for")
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

        # 2. Extract Confidence Features & Calibrated Confidence
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

        conf_service = ConfidenceCalibrationService()
        conf_pred = conf_service.compute_confidence_and_decision(
            features=features,
            verification_summary=ver_summary,
            ticket_id=target_issue_id,
            resolution_run_id=target_res_run.run_id,
            session=session
        )

        # 3. Routing Engine Prediction
        retrieved_cases = [
            {"issue_id": 101, "labels": ["area/terminal"], "title": "Integrated terminal pty crash"},
            {"issue_id": 102, "labels": ["area/terminal"], "title": "PowerShell terminal exit code 1"}
        ]
        routing_service = RoutingEngineService()
        routing_res = routing_service.predict_route(
            retrieved_cases=retrieved_cases,
            ticket_id=target_issue_id,
            session=session
        )

        # 4. Deterministic Decision Engine
        dec_engine = DeterministicDecisionEngine()
        final_dec = dec_engine.make_final_decision(
            ticket_id=target_issue_id,
            ticket_title=issue_title,
            severity_level="medium",
            is_duplicate=False,
            root_cause_cluster="Terminal Shell Crashes",
            retrieved_cases=retrieved_cases,
            resolution_data=res_data,
            verification_summary=ver_summary,
            confidence_pred=conf_pred,
            routing_res=routing_res,
            session=session
        )

        # Render Formatted Final Report
        report = render_human_readable_decision(final_dec)
        print(report)


if __name__ == "__main__":
    main()
