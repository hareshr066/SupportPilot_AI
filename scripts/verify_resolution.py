import sys
import logging
import argparse
from pathlib import Path

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.session import get_db
from app.database.models import ResolutionRun
from app.services.claim_verification_service import (
    ClaimVerificationService,
    render_human_readable_verification,
)
from sqlalchemy import select

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("verify_resolution")


def main():
    parser = argparse.ArgumentParser(
        description="SupportPilot - Independent Claim Verification CLI"
    )
    parser.add_argument("--resolution-run-id", type=str, default=None, help="ResolutionRun ID or run_id to verify")
    parser.add_argument("--latest", action="store_true", help="Verify latest resolution run in database")

    args = parser.parse_args()

    with get_db() as session:
        target_id = args.resolution_run_id

        if args.latest or not target_id:
            latest_run = session.scalar(
                select(ResolutionRun).order_by(ResolutionRun.id.desc()).limit(1)
            )
            if not latest_run:
                logger.error("No ResolutionRun records found in database. Run resolution generation first.")
                sys.exit(1)
            target_id = latest_run.run_id
            logger.info(f"Targeting latest resolution run: {target_id}")

        service = ClaimVerificationService(db_session=session)
        summary = service.verify_resolution(resolution_run_id=target_id, session=session)

        rendered = render_human_readable_verification(summary)
        print(rendered)


if __name__ == "__main__":
    main()
