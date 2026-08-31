import sys
import logging
import argparse
import numpy as np
from pathlib import Path

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.session import get_db
from app.database.models import ConfidenceRun
from app.services.confidence_service import (
    ConfidenceCalibrationService,
    calculate_brier_score,
    calculate_ece,
)
from sqlalchemy import select

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("evaluate_calibration")


def main():
    parser = argparse.ArgumentParser(description="SupportPilot - Evaluate Calibration across Database Runs")
    parser.add_argument("--limit", type=int, default=20, help="Max confidence runs to evaluate")

    args = parser.parse_args()

    with get_db() as session:
        runs = session.scalars(
            select(ConfidenceRun).order_by(ConfidenceRun.id.desc()).limit(args.limit)
        ).all()

        if not runs:
            logger.info("No ConfidenceRun records found in database.")
            print("\n=======================================================================")
            print("                 CONFIDENCE CALIBRATION EVALUATION                     ")
            print("=======================================================================")
            print("  Evaluated Runs:                 0")
            print("  Status:                         INSUFFICIENT_CALIBRATION_DATA")
            print("=======================================================================\n")
            sys.exit(0)

        probas = [r.calibrated_confidence for r in runs]
        # Empirical target proxy: AUTO_RESOLVE decision without contradiction
        y_true = [1 if r.decision == "AUTO_RESOLVE" else 0 for r in runs]

        brier = calculate_brier_score(y_true, probas)
        ece, mce, bin_table = calculate_ece(y_true, probas, n_bins=5)

        print("\n=======================================================================")
        print("                 CONFIDENCE CALIBRATION EVALUATION                     ")
        print("=======================================================================")
        print(f"  EVALUATED DATABASE RUNS:        {len(runs)}")
        print(f"  BRIER SCORE:                    {brier:.4f}")
        print(f"  EXPECTED CALIBRATION ERROR:     {ece * 100:.2f}%")
        print(f"  MAXIMUM CALIBRATION ERROR:      {mce * 100:.2f}%")
        print("-----------------------------------------------------------------------")
        print("  RELIABILITY BINS:")
        for b in bin_table:
            print(f"    Bin [{b['bin']}]: Count={b['count']:<3} | Mean Conf={b['mean_confidence']:.2f} | Acc={b['observed_accuracy']:.2f} | Gap={b['calibration_gap']:.2f}")
        print("=======================================================================\n")


if __name__ == "__main__":
    main()
