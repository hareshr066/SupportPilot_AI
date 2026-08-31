import sys
import logging
import argparse
from pathlib import Path

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.schemas.pipeline_schemas import TicketInput
from app.services.pipeline_orchestrator import run_support_pipeline

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("run_pipeline")


def main():
    parser = argparse.ArgumentParser(description="SupportPilot - Run End-to-End Orchestrated Pipeline")
    parser.add_argument("--issue-id", type=int, default=None, help="Database Issue ID to run pipeline for")
    parser.add_argument("--repository-id", type=int, default=1, help="Repository ID if testing raw ticket")
    parser.add_argument("--title", type=str, default=None, help="Raw ticket title string")
    parser.add_argument("--body", type=str, default="", help="Raw ticket body string")

    args = parser.parse_args()

    if args.issue_id:
        ticket = TicketInput(
            ticket_id=args.issue_id,
            repository_id=args.repository_id,
            title=f"Issue #{args.issue_id}",
            body=""
        )
    elif args.title:
        ticket = TicketInput(
            repository_id=args.repository_id,
            title=args.title,
            body=args.body
        )
    else:
        # Default test ticket
        ticket = TicketInput(
            ticket_id=1,
            repository_id=1,
            title="Terminal shell process terminated unexpectedly with exit code 1",
            body="When launching PowerShell in integrated terminal on Windows 11, the pty host process crashes."
        )

    logger.info(f"Executing SupportPilot LangGraph pipeline for ticket '{ticket.title}'...")
    res = run_support_pipeline(ticket)

    print("\n==================================================")
    print("           SUPPORTPILOT PIPELINE                  ")
    print("==================================================")
    print(f"Pipeline Run ID:     {res.pipeline_run_id}")
    print(f"Ticket ID:           {res.ticket_id or 'N/A'}")
    print(f"Status:              {res.status}")
    print("--------------------------------------------------")
    print(f"Severity:            {res.severity.get('predicted_severity', 'N/A') if res.severity else 'N/A'}")
    print(f"Duplicate:           {'Yes' if res.duplicate and res.duplicate.get('is_duplicate') else 'No'}")
    print(f"Root Cause:          {res.root_cause.get('cluster_name', 'N/A') if res.root_cause else 'N/A'}")
    print(f"Retrieved Cases:     {len(res.retrieval.get('retrieved_cases', [])) if res.retrieval else 0}")
    print(f"Resolution Status:   {'Generated' if res.resolution else 'N/A'}")
    print(f"Verification Verdict:{res.verification.get('overall_faithfulness_status', 'N/A') if res.verification else 'N/A'}")
    print(f"Calibrated Confidence:{res.calibrated_confidence * 100:.2f}%")
    print(f"Routing Target:      {res.routing.get('predicted_component', 'N/A') if res.routing else 'N/A'} -> {res.recommended_team}")
    print("--------------------------------------------------")
    print(f"FINAL DECISION:      {res.final_decision}")
    print(f"HUMAN REVIEW NEEDED: {res.human_review_required}")
    print(f"TOTAL LATENCY:       {res.total_latency_ms:.2f} ms")
    print("--------------------------------------------------")
    print("STAGE LATENCIES:")
    for stage, lat in res.stage_latencies.items():
        status_str = res.stage_statuses.get(stage, "UNKNOWN")
        print(f"  - {stage:<25}: {lat:>7.2f} ms [{status_str}]")
    print("--------------------------------------------------")
    print(f"AUDIT REFERENCE:     {res.audit_reference}")
    print("==================================================\n")


if __name__ == "__main__":
    main()
