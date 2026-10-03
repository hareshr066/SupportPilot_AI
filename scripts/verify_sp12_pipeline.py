import json
import time
from fastapi.testclient import TestClient
from sqlalchemy import select, func, desc

from app.api.main import app
from app.database.session import SessionLocal
from app.database.models import Issue, Repository, PipelineRun, PipelineStageRun

def main():
    client = TestClient(app)

    print("=== Step 1: Checking Ticket SP-12 in PostgreSQL ===")
    session = SessionLocal()
    ticket_id_str = "SP-12"
    db_id = 12

    issue = session.scalar(select(Issue).where(Issue.id == db_id))
    if not issue:
        print(f"Ticket SP-12 not found in DB. Creating SP-12 for verification...")
        # Get or create StudySync repository
        repo = session.scalar(select(Repository).where(Repository.owner == "StudySync"))
        if not repo:
            repo = Repository(
                owner="StudySync",
                name="main",
                full_name="StudySync/main",
                html_url="https://github.com/StudySync/main",
                enabled=True,
                auto_analysis_enabled=True
            )
            session.add(repo)
            session.commit()
            session.refresh(repo)

        issue = Issue(
            id=12,
            github_issue_id=12000,
            repository_id=repo.id,
            issue_number=12,
            title="Study progress resets after refresh",
            body="After reviewing flashcards, today's study progress disappears after refreshing the application.",
            state="RECEIVED",
            html_url="https://supportpilot.internal/tickets/SP-12"
        )
        session.add(issue)
        session.commit()
        session.refresh(issue)

    print(f"Found Ticket SP-12 in PostgreSQL:")
    print(f"  - DB ID: {issue.id}")
    print(f"  - Application: {issue.repository.owner if issue.repository else 'StudySync'}")
    print(f"  - Title: {issue.title}")
    print(f"  - Status: {issue.state}")
    print(f"  - Description: {issue.body}")

    print("\n=== Step 2: Triggering POST /v1/tickets/SP-12/analyze ===")
    t0 = time.time()
    res_analyze = client.post(f"/v1/tickets/{ticket_id_str}/analyze")
    t1 = time.time()
    total_time_ms = round((t1 - t0) * 1000, 2)

    print(f"POST /v1/tickets/{ticket_id_str}/analyze Status: {res_analyze.status_code}")
    print(f"Execution Time: {total_time_ms} ms")

    if res_analyze.status_code != 200:
        print(f"ERROR: Analyze endpoint failed with status {res_analyze.status_code}: {res_analyze.text}")
        session.close()
        return

    analyze_data = res_analyze.json()
    run_id = analyze_data.get("pipeline_run_id")
    print(f"Pipeline Run ID: {run_id}")

    print("\n=== Step 3: Inspecting Pipeline Run Record in PostgreSQL ===")
    run_rec = session.scalar(select(PipelineRun).where(PipelineRun.pipeline_run_id == run_id))
    if not run_rec:
        print(f"ERROR: PipelineRun record '{run_id}' NOT found in PostgreSQL!")
    else:
        print(f"PipelineRun Record Persisted:")
        print(f"  - Run ID: {run_rec.pipeline_run_id}")
        print(f"  - Ticket ID: {run_rec.ticket_id}")
        print(f"  - Status: {run_rec.status}")
        print(f"  - Final Decision: {run_rec.final_decision}")
        print(f"  - Recommended Team: {run_rec.recommended_team}")
        print(f"  - Calibrated Confidence: {run_rec.calibrated_confidence}")
        print(f"  - Total Latency: {run_rec.total_latency_ms} ms")

    print("\n=== Step 4: Inspecting Persisted Stage Runs in PostgreSQL ===")
    stage_recs = session.scalars(
        select(PipelineStageRun).where(PipelineStageRun.pipeline_run_id == run_id).order_by(PipelineStageRun.id)
    ).all()
    
    print(f"Found {len(stage_recs)} stage run records in PostgreSQL:")
    for stg in stage_recs:
        print(f"  - [{stg.stage_name}] Status: {stg.status} | Latency: {stg.latency_ms} ms | Error: {stg.error_code}")

    print("\n=== Step 5: Testing GET /v1/runs/{run_id} ===")
    res_get_run = client.get(f"/v1/runs/{run_id}")
    print(f"GET /v1/runs/{run_id} Status: {res_get_run.status_code}")
    if res_get_run.status_code == 200:
        run_get_data = res_get_run.json()
        print(f"Retrieved Run Data: {json.dumps(run_get_data, indent=2)}")

    session.close()

if __name__ == "__main__":
    main()
