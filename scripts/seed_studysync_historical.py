import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, ".")

from sqlalchemy import select, func
from config import settings
from app.database.session import get_db
from app.database.models import (
    Issue,
    Repository,
    Comment,
    PullRequest,
    Label,
    User,
    IssueEmbedding,
    issue_pull_requests,
    issue_labels,
)
from app.services.embedding_service import EmbeddingService
from app.services.hybrid_retrieval_service import HybridRetrievalService

HISTORICAL_STUDYSYNC_CASES = [
    {
        "issue_number": 101,
        "github_issue_id": 900101,
        "title": "Study progress resets after page refresh due to missing localStorage sync on unload",
        "body": (
            "Users reported that refreshing the browser page during an active study session or module resets their progress back to 0%. "
            "Technical investigation revealed that the in-memory state in StudySessionContainer.tsx was not flushing unsaved progress vectors "
            "to localStorage or dispatching a sync payload to the backend REST API before window unload."
        ),
        "resolution_comment": (
            "FIX RESOLVED: Fixed by adding a window 'beforeunload' event listener in StudySessionContainer.tsx that flushes "
            "current module study progress state to localStorage and dispatches a synchronous beacon payload to /api/v1/study-progress/sync. "
            "Verified progress state persists seamlessly after hard refresh."
        ),
        "pr_number": 501,
        "pr_title": "PR #501: Fix study session progress state persistence on page refresh",
        "pr_url": "https://github.com/StudySync/main/pull/501",
        "labels": ["bug", "persistence", "frontend", "state-management"]
    },
    {
        "issue_number": 102,
        "github_issue_id": 900102,
        "title": "Flashcard completion status not persisted across browser restarts",
        "body": (
            "Flashcard completion status was resetting when users closed and reopened the desktop app. "
            "The offline sync worker ignored HTTP 204 responses from the card completion endpoint."
        ),
        "resolution_comment": (
            "FIX RESOLVED: Updated sync worker status handler to treat HTTP 200 and 204 responses as successful sync completions. "
            "Card completion flags now persist accurately."
        ),
        "pr_number": 502,
        "pr_title": "PR #502: Accept 204 status in flashcard completion sync worker",
        "pr_url": "https://github.com/StudySync/main/pull/502",
        "labels": ["bug", "flashcards", "sync"]
    },
    {
        "issue_number": 103,
        "github_issue_id": 900103,
        "title": "Deck cards fail to load after reopening study session",
        "body": (
            "Reopening a study deck threw a TypeError when parsing deck metadata if any assigned tag was deleted. "
            "This caused the card loader component to crash silently."
        ),
        "resolution_comment": (
            "FIX RESOLVED: Added null guard check in DeckCardLoader for deleted tag references, falling back to empty tag array."
        ),
        "pr_number": 503,
        "pr_title": "PR #503: Handle deleted tags gracefully in deck loader",
        "pr_url": "https://github.com/StudySync/main/pull/503",
        "labels": ["bug", "deck-loader", "null-pointer"]
    },
    {
        "issue_number": 104,
        "github_issue_id": 900104,
        "title": "Study room disconnects unexpectedly after 5 minutes of inactivity",
        "body": (
            "Active collaborative study rooms were dropping WebSocket connections after 5 minutes of inactivity. "
            "The load balancer TCP idle timeout was 45s while client ping interval was 60s."
        ),
        "resolution_comment": (
            "FIX RESOLVED: Reduced WebSocket client heartbeat ping interval to 30s and enabled automatic exponential reconnect."
        ),
        "pr_number": 504,
        "pr_title": "PR #504: Reduce WebSocket ping interval and enable auto-reconnect",
        "pr_url": "https://github.com/StudySync/main/pull/504",
        "labels": ["network", "websocket", "study-rooms"]
    },
    {
        "issue_number": 105,
        "github_issue_id": 900105,
        "title": "Shared deck changes do not appear immediately for collaborative study groups",
        "body": (
            "Changes made to shared study decks were not visible to group members until manual app restart due to aggressive IndexedDB caching."
        ),
        "resolution_comment": (
            "FIX RESOLVED: Implemented stale-while-revalidate caching policy for shared deck API responses and ETag header validation."
        ),
        "pr_number": 505,
        "pr_title": "PR #505: Invalidate shared deck IndexedDB cache on ETag mismatch",
        "pr_url": "https://github.com/StudySync/main/pull/505",
        "labels": ["caching", "indexeddb", "shared-decks"]
    },
    {
        "issue_number": 106,
        "github_issue_id": 900106,
        "title": "Spaced repetition review date calculated incorrectly after leap year boundary",
        "body": (
            "SM-2 spaced repetition review dates calculated incorrect interval offsets across year boundaries due to hardcoded 365-day year constants."
        ),
        "resolution_comment": (
            "FIX RESOLVED: Replaced static integer day calculations with date-fns addDays utility."
        ),
        "pr_number": 506,
        "pr_title": "PR #506: Use date-fns for spaced repetition interval math",
        "pr_url": "https://github.com/StudySync/main/pull/506",
        "labels": ["algorithm", "spaced-repetition", "dates"]
    },
    {
        "issue_number": 107,
        "github_issue_id": 900107,
        "title": "Authentication session expires unexpectedly during active quiz sessions",
        "body": (
            "Users were logged out mid-quiz because access token refresh requests were not extending the sliding refresh cookie."
        ),
        "resolution_comment": (
            "FIX RESOLVED: Updated auth middleware to extend sliding JWT expiration on active API calls."
        ),
        "pr_number": 507,
        "pr_title": "PR #507: Implement sliding expiration for StudySync JWT tokens",
        "pr_url": "https://github.com/StudySync/main/pull/507",
        "labels": ["auth", "jwt", "session"]
    },
    {
        "issue_number": 108,
        "github_issue_id": 900108,
        "title": "Study statistics show incorrect daily count across timezone boundaries",
        "body": (
            "Daily card review statistics were aggregated using UTC midnight instead of the user's local timezone, causing study streaks to break."
        ),
        "resolution_comment": (
            "FIX RESOLVED: Passed user timezone header to daily stats aggregation query in PostgreSQL."
        ),
        "pr_number": 508,
        "pr_title": "PR #508: Aggregate daily study stats in user local timezone",
        "pr_url": "https://github.com/StudySync/main/pull/508",
        "labels": ["analytics", "timezone", "stats"]
    },
    {
        "issue_number": 109,
        "github_issue_id": 900109,
        "title": "Card creation fails with certain LaTeX math inputs",
        "body": (
            "Card creation form threw an unhandled parser exception when card text contained raw LaTeX backslashes."
        ),
        "resolution_comment": (
            "FIX RESOLVED: Added escaping for raw LaTeX backslashes prior to sanitization pass in CardEditor component."
        ),
        "pr_number": 509,
        "pr_title": "PR #509: Escape backslashes in card LaTeX formula parser",
        "pr_url": "https://github.com/StudySync/main/pull/509",
        "labels": ["latex", "card-editor", "parsing"]
    },
    {
        "issue_number": 110,
        "github_issue_id": 900110,
        "title": "WebSocket study room stops receiving updates during background tab throttling",
        "body": (
            "When the StudySync browser tab was placed in the background, Chrome timer throttling paused the WebSocket message queue."
        ),
        "resolution_comment": (
            "FIX RESOLVED: Migrated realtime study room message queue processing into a Web Worker thread to bypass tab throttling."
        ),
        "pr_number": 510,
        "pr_title": "PR #510: Process study room WebSocket queue inside Web Worker",
        "pr_url": "https://github.com/StudySync/main/pull/510",
        "labels": ["websocket", "web-worker", "background-sync"]
    }
]


def seed_studysync_corpus():
    print("==================================================")
    print("  SEEDING HISTORICAL RESOLVED STUDYSYNC CORPUS    ")
    print("==================================================")

    now = datetime.now(timezone.utc)
    one_day = timedelta(days=1)

    with get_db() as session:
        # 1. Ensure StudySync Repository exists (ID 2)
        repo = session.scalar(select(Repository).where(Repository.full_name == "StudySync/main"))
        if not repo:
            repo = session.scalar(select(Repository).where(Repository.id == 2))
        if not repo:
            repo = Repository(
                id=2,
                github_repository_id=99002,
                owner="StudySync",
                name="main",
                full_name="StudySync/main",
                html_url="https://github.com/StudySync/main",
                enabled=True,
                created_at=now - timedelta(days=30),
                updated_at=now
            )
            session.add(repo)
            session.flush()

        print(f"Target Repository: ID={repo.id}, FullName={repo.full_name}")

        # 2. Ensure default system user exists for authorship
        user = session.scalar(select(User).where(User.login == "studysync-bot"))
        if not user:
            user = User(github_user_id=88001, login="studysync-bot")
            session.add(user)
            session.flush()

        created_issues_count = 0

        # 3. Seed historical closed issues
        for idx, item in enumerate(HISTORICAL_STUDYSYNC_CASES):
            num = item["issue_number"]
            existing = session.scalar(
                select(Issue).where(
                    Issue.repository_id == repo.id,
                    Issue.issue_number == num
                )
            )

            created_time = now - timedelta(days=20 - idx)
            closed_time = created_time + timedelta(hours=6)

            if not existing:
                iss = Issue(
                    github_issue_id=item["github_issue_id"],
                    repository_id=repo.id,
                    issue_number=num,
                    title=item["title"],
                    body=item["body"],
                    state="closed",
                    state_reason="completed",
                    author_id=user.id,
                    created_at=created_time,
                    closed_at=closed_time,
                    html_url=f"https://github.com/StudySync/main/issues/{num}"
                )
                session.add(iss)
                session.flush()
                created_issues_count += 1
            else:
                iss = existing
                iss.title = item["title"]
                iss.body = item["body"]
                iss.state = "closed"
                iss.state_reason = "completed"
                iss.closed_at = closed_time
                session.flush()

            # Resolution Comment
            comment_text = item["resolution_comment"]
            existing_comment = session.scalar(
                select(Comment).where(
                    Comment.issue_id == iss.id,
                    Comment.body == comment_text
                )
            )
            if not existing_comment:
                c = Comment(
                    github_comment_id=950000 + num,
                    issue_id=iss.id,
                    author_id=user.id,
                    body=comment_text,
                    created_at=closed_time,
                    html_url=f"https://github.com/StudySync/main/issues/{num}#issuecomment-1"
                )
                session.add(c)
                session.flush()

            # Linked PR
            pr_num = item["pr_number"]
            existing_pr = session.scalar(
                select(PullRequest).where(
                    PullRequest.repository_id == repo.id,
                    PullRequest.pr_number == pr_num
                )
            )
            if not existing_pr:
                pr = PullRequest(
                    github_pr_id=980000 + pr_num,
                    repository_id=repo.id,
                    pr_number=pr_num,
                    html_url=item["pr_url"]
                )
                session.add(pr)
                session.flush()
                
                # Link issue to PR
                session.execute(
                    issue_pull_requests.insert().values(issue_id=iss.id, pull_request_id=pr.id)
                )

        session.commit()
        print(f"Successfully processed {len(HISTORICAL_STUDYSYNC_CASES)} historical closed StudySync issues ({created_issues_count} new).")

        # 4. Generate Embeddings for StudySync Repository (Repo ID 2)
        print("\n--- GENERATING VECTOR EMBEDDINGS FOR STUDYSYNC ---")
        emb_svc = EmbeddingService()
        emb_res = emb_svc.generate_embeddings_for_repository(repository_id=repo.id, db_session=session, force=True)
        print(f"Embedding Result: {emb_res}")

        # 5. Build BM25 Inverted Index across entire corpus
        print("\n--- BUILDING BM25 INVERTED INDEX ---")
        ret_svc = HybridRetrievalService(db_session=session)
        bm25_res = ret_svc.build_retrieval_index(session, repository_id=None)
        print(f"BM25 Index Result: {bm25_res}")

        session.commit()

        # 6. Verification Audit
        total_studysync_issues = session.scalar(select(func.count(Issue.id)).where(Issue.repository_id == repo.id))
        closed_studysync_issues = session.scalar(select(func.count(Issue.id)).where(Issue.repository_id == repo.id, Issue.state == "closed"))
        embeddings_studysync = session.scalar(
            select(func.count(IssueEmbedding.id))
            .join(Issue, IssueEmbedding.issue_id == Issue.id)
            .where(Issue.repository_id == repo.id)
        )

        print("\n==================================================")
        print("    STUDYSYNC CORPUS SEEDING VERIFICATION         ")
        print("==================================================")
        print(f"StudySync Total Issues in DB: {total_studysync_issues}")
        print(f"StudySync Closed Historical Issues: {closed_studysync_issues}")
        print(f"StudySync Vector Embeddings: {embeddings_studysync}")
        print(f"BM25 Document Count: {bm25_res.get('document_count')}")
        print("==================================================")

if __name__ == "__main__":
    seed_studysync_corpus()
