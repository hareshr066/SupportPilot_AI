import sys
import logging
import argparse
import numpy as np
from pathlib import Path

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.session import get_db
from app.database.models import RoutingPrediction
from app.services.routing_service import RoutingEngineService
from sqlalchemy import select

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("evaluate_routing")


def main():
    parser = argparse.ArgumentParser(description="SupportPilot - Evaluate Routing Predictions")
    parser.add_argument("--limit", type=int, default=20, help="Max database prediction records to evaluate")
    args = parser.parse_args()

    with get_db() as session:
        preds = session.scalars(
            select(RoutingPrediction).order_by(RoutingPrediction.id.desc()).limit(args.limit)
        ).all()

        if not preds:
            logger.info("No RoutingPrediction records found in database.")
            print("\n=======================================================================")
            print("                 ROUTING MODEL EVALUATION REPORT                       ")
            print("=======================================================================")
            print("  Evaluated Records:              0")
            print("  Status:                         INSUFFICIENT_ROUTING_DATA")
            print("=======================================================================\n")
            sys.exit(0)

        probas = [p.routing_probability for p in preds]
        avg_prob = float(np.mean(probas)) if probas else 0.0

        print("\n=======================================================================")
        print("                 ROUTING MODEL EVALUATION REPORT                       ")
        print("=======================================================================")
        print(f"  EVALUATED DATABASE PREDICTIONS: {len(preds)}")
        print(f"  MEAN ROUTING CONFIDENCE:        {avg_prob * 100:.2f}%")
        print("-----------------------------------------------------------------------")
        print("  RECENT PREDICTIONS:")
        for p in preds[:5]:
            print(f"    - ID: {p.routing_prediction_id:<25} | Comp: {p.predicted_component:<15} | Conf: {p.routing_probability * 100:.1f}%")
        print("=======================================================================\n")


if __name__ == "__main__":
    main()
