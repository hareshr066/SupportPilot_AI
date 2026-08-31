import sys
import logging
import argparse
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.session import get_db
from app.database.models import ResolutionRun, VerificationRun, ClaimVerificationRecord
from app.services.claim_verification_service import ClaimVerificationService
from sqlalchemy import select

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("evaluate_verification")


def main():
    parser = argparse.ArgumentParser(
        description="SupportPilot - Evaluate Claim Verification & Compare Citation-Only Baseline"
    )
    parser.add_argument("--limit", type=int, default=10, help="Max resolution runs to evaluate")

    args = parser.parse_args()

    with get_db() as session:
        runs = session.scalars(
            select(ResolutionRun).order_by(ResolutionRun.id.desc()).limit(args.limit)
        ).all()

        if not runs:
            logger.warning("No ResolutionRun records found in database to evaluate.")
            print("\n=======================================================================")
            print("                CLAIM VERIFICATION EVALUATION                          ")
            print("=======================================================================")
            print("  Evaluated Resolution Runs:     0")
            print("  Annotated Ground-Truth Claims:  0 (Insufficient ground truth)")
            print("=======================================================================\n")
            sys.exit(0)

        service = ClaimVerificationService(db_session=session)

        sem_faithfulness_list = []
        sem_citation_cov_list = []
        sem_unsupported_list = []
        sem_contradiction_list = []

        base_faithfulness_list = []
        base_unsupported_list = []

        total_claims_evaluated = 0

        for r_run in runs:
            summary = service.verify_resolution(r_run.run_id, session)
            total_claims_evaluated += summary.total_claims

            sem_faithfulness_list.append(summary.strict_faithfulness)
            sem_citation_cov_list.append(summary.citation_coverage)
            sem_unsupported_list.append(summary.unsupported_claim_rate)
            sem_contradiction_list.append(summary.contradiction_rate)

            # Baseline: Citation-Only Verifier (marks claim SUPPORTED if valid source ID exists)
            base_supported = sum(1 for c in summary.claim_results if c.source_ids)
            tot = max(1, summary.total_claims)
            base_faithfulness_list.append(base_supported / float(tot))
            base_unsupported_list.append((tot - base_supported) / float(tot))

        n_runs = len(runs)

        print("\n=======================================================================")
        print("          CLAIM VERIFICATION & BASELINE COMPARISON REPORT              ")
        print("=======================================================================")
        print(f"  Evaluated Resolution Runs:      {n_runs}")
        print(f"  Total Claims Evaluated:         {total_claims_evaluated}")
        print("-----------------------------------------------------------------------")
        print("  METRIC                         SEMANTIC VERIFIER   CITATION-ONLY BASELINE")
        print("-----------------------------------------------------------------------")
        print(f"  Strict Faithfulness Rate:       {np.mean(sem_faithfulness_list) * 100:6.1f}%             {np.mean(base_faithfulness_list) * 100:6.1f}%")
        print(f"  Citation Coverage:              {np.mean(sem_citation_cov_list) * 100:6.1f}%             {np.mean(sem_citation_cov_list) * 100:6.1f}%")
        print(f"  Unsupported Claim Rate:         {np.mean(sem_unsupported_list) * 100:6.1f}%             {np.mean(base_unsupported_list) * 100:6.1f}%")
        print(f"  Contradiction Rate:             {np.mean(sem_contradiction_list) * 100:6.1f}%                  N/A (0.0%)")
        print("-----------------------------------------------------------------------")
        print("  NOTE: Citation-Only baseline falsely considers any cited claim as supported,")
        print("  whereas Semantic Verifier checks factual alignment against source evidence.")
        print("=======================================================================\n")


if __name__ == "__main__":
    main()
