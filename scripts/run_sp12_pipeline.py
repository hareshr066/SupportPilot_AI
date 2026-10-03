import os
import sys
import json
from datetime import datetime, timezone

WORKSPACE_ROOT = os.path.abspath(".")
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from app.schemas.pipeline_schemas import TicketInput
from app.services.pipeline_orchestrator import run_support_pipeline
from app.database.session import get_db
from app.database.models import Issue

def run_sp12():
    print("=" * 60)
    print("EXECUTING REAL PIPELINE FOR SP-12")
    print("=" * 60)

    # 1. Fetch SP-12 ticket info from DB if possible
    ticket_id = 12
    title = "Study progress resets after refresh"
    body = "Study progress resets after page refresh due to missing localStorage sync on unload."
    repo_id = 2

    with get_db() as session:
        issue = session.query(Issue).filter_by(id=12).first()
        if issue:
            ticket_id = issue.id
            title = issue.title
            body = issue.body or ""
            repo_id = issue.repository_id
            print(f"Loaded SP-12 from DB: ID={ticket_id}, RepoID={repo_id}, Title='{title}'")
        else:
            print(f"Using fallback SP-12 info: RepoID={repo_id}, Title='{title}'")

    ticket_input = TicketInput(
        ticket_id=ticket_id,
        repository_id=repo_id,
        title=title,
        body=body
    )

    t0 = datetime.now(timezone.utc)
    result = run_support_pipeline(ticket=ticket_input)
    t1 = datetime.now(timezone.utc)

    print("\n" + "=" * 60)
    print(f"PIPELINE RUN COMPLETE ({result.pipeline_run_id})")
    print("=" * 60)
    print(f"Status: {result.status}")
    print(f"Final Decision: {result.final_decision}")
    print(f"Human Review Required: {result.human_review_required}")
    print(f"Calibrated Confidence: {result.calibrated_confidence}")
    print(f"Total Latency: {result.total_latency_ms:.1f} ms")

    print("\nSTAGE DETAILS:")
    print(f"1. Severity: {result.severity}")
    print(f"2. Duplicate: {result.duplicate}")
    print(f"3. Root Cause: {result.root_cause}")
    print(f"4. Retrieval: {result.retrieval}")
    print(f"5. Resolution: {result.resolution}")
    print(f"6. Verification: {result.verification}")
    print(f"7. Confidence: {result.confidence}")
    print(f"8. Routing: {result.routing}")

    # Output detailed report to file
    dump = {
        "pipeline_run_id": result.pipeline_run_id,
        "ticket_id": result.ticket_id,
        "status": result.status,
        "final_decision": result.final_decision,
        "recommended_team": result.recommended_team,
        "calibrated_confidence": result.calibrated_confidence,
        "human_review_required": result.human_review_required,
        "total_latency_ms": result.total_latency_ms,
        "stage_latencies": result.stage_latencies,
        "stage_statuses": result.stage_statuses,
        "severity": result.severity,
        "duplicate": result.duplicate,
        "root_cause": result.root_cause,
        "retrieval": result.retrieval,
        "resolution": result.resolution,
        "verification": result.verification,
        "confidence": result.confidence,
        "routing": result.routing,
        "decision": result.decision
    }

    with open("sp12_pipeline_run_output.json", "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2)

    print("\nDetailed output written to sp12_pipeline_run_output.json")

if __name__ == "__main__":
    run_sp12()
