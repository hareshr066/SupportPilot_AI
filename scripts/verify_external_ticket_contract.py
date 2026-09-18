import json
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.database.session import SessionLocal
from app.database.models import Issue, Repository

def main():
    client = TestClient(app)
    
    print("=== Step 1: Testing POST /v1/tickets with StudySync payload ===")
    studysync_payload = {
        "title": "Study progress resets after refresh",
        "description": "After reviewing flashcards, today's study progress disappears after refreshing the application.",
        "application": "StudySync",
        "environment": "production",
        "feature": "study-progress"
    }

    res_post = client.post("/v1/tickets", json=studysync_payload)
    print(f"POST /v1/tickets Status: {res_post.status_code}")
    print(f"POST Response: {res_post.text}")
    assert res_post.status_code == 201, f"Expected 201, got {res_post.status_code}"
    ticket_data = res_post.json()
    ticket_id = ticket_data["ticket_id"]
    print(f"Generated Ticket ID: {ticket_id}")

    print("\n=== Step 2: Direct PostgreSQL Verification ===")
    numeric_id = int(ticket_id.replace("SP-", ""))
    session = SessionLocal()
    try:
        issue = session.scalar(select(Issue).where(Issue.id == numeric_id))
        assert issue is not None, f"Issue with DB ID {numeric_id} not found in PostgreSQL!"
        print(f"PostgreSQL Verification SUCCESS:")
        print(f"  - DB Issue ID: {issue.id}")
        print(f"  - Repository ID: {issue.repository_id} ({issue.repository.full_name})")
        print(f"  - Title: {issue.title}")
        print(f"  - Body: {issue.body}")
        print(f"  - State: {issue.state}")
        print(f"  - Created At: {issue.created_at}")
    finally:
        session.close()

    print("\n=== Step 3: Testing GET /v1/tickets and GET /v1/tickets/{ticket_id} ===")
    res_list = client.get("/v1/tickets")
    print(f"GET /v1/tickets Status: {res_list.status_code}")
    assert res_list.status_code == 200

    res_get = client.get(f"/v1/tickets/{ticket_id}")
    print(f"GET /v1/tickets/{ticket_id} Status: {res_get.status_code}")
    print(f"GET Response: {res_get.text}")
    assert res_get.status_code == 200
    assert res_get.json()["ticket_id"] == ticket_id

    print("\n=== Step 4: Testing POST /v1/tickets/{ticket_id}/analyze ===")
    res_analyze = client.post(f"/v1/tickets/{ticket_id}/analyze")
    print(f"POST /v1/tickets/{ticket_id}/analyze Status: {res_analyze.status_code}")
    assert res_analyze.status_code == 200
    analyze_data = res_analyze.json()
    print(f"Analyze Response Summary:")
    print(f"  - Pipeline Run ID: {analyze_data.get('pipeline_run_id')}")
    print(f"  - Status: {analyze_data.get('status')}")
    print(f"  - Final Decision: {analyze_data.get('final_decision')}")
    print(f"  - Recommended Team: {analyze_data.get('recommended_team')}")
    print(f"  - Human Review Required: {analyze_data.get('human_review_required')}")

    print("\n=== Step 5: Testing GET /v1/runs/{run_id} ===")
    run_id = analyze_data.get('pipeline_run_id')
    res_run = client.get(f"/v1/runs/{run_id}")
    print(f"GET /v1/runs/{run_id} Status: {res_run.status_code}")
    assert res_run.status_code == 200

    print("\nALL CONTRACT VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
