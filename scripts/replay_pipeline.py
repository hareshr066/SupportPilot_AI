import sys
import logging
import argparse
from pathlib import Path

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.services.pipeline_orchestrator import replay_pipeline_run

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("replay_pipeline")


def main():
    parser = argparse.ArgumentParser(description="SupportPilot - Replay Pipeline Run from Database")
    parser.add_argument("--run-id", type=str, required=True, help="Pipeline Run ID string (e.g. pipeline_123456)")
    args = parser.parse_args()

    logger.info(f"Replaying historical pipeline run '{args.run_id}' from database...")
    res = replay_pipeline_run(args.run_id)

    if not res:
        logger.error(f"Pipeline run '{args.run_id}' not found in database.")
        sys.exit(1)

    print("\n==================================================")
    print("           SUPPORTPILOT PIPELINE REPLAY           ")
    print("==================================================")
    print(f"Pipeline Run ID:     {res.pipeline_run_id}")
    print(f"Ticket ID:           {res.ticket_id or 'N/A'}")
    print(f"Status:              {res.status}")
    print(f"Final Decision:      {res.final_decision}")
    print(f"Recommended Team:    {res.recommended_team}")
    print(f"Total Latency:       {res.total_latency_ms:.2f} ms")
    print("--------------------------------------------------")
    print("REPLAYED STAGE STATUSES & LATENCIES:")
    for stage, lat in res.stage_latencies.items():
        st = res.stage_statuses.get(stage, "UNKNOWN")
        print(f"  - {stage:<25}: {lat:>7.2f} ms [{st}]")
    print("--------------------------------------------------")
    print(f"Audit Reference:     {res.audit_reference}")
    print("==================================================\n")


if __name__ == "__main__":
    main()
