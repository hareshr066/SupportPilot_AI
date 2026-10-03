import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from app.database.models import (
    Base,
    Repository,
    Issue,
    Comment,
    PullRequest,
    IssueEmbedding,
    PipelineRun,
    PipelineStageRun,
    ResolutionRun,
    ResolutionClaimRecord,
    VerificationRun,
    ClaimVerificationRecord,
    ConfidenceRun,
    DecisionRun,
    WebhookEvent,
)
from app.services.retention_service import (
    RetentionService,
    calculate_storage_threshold_status,
    PROTECTED_KNOWLEDGE_TABLES,
    ELIGIBLE_TELEMETRY_TABLES,
)


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_retention_cutoff_calculation():
    service = RetentionService(
        pipeline_days=90,
        stage_days=60,
        webhook_days=30,
        evaluation_days=90,
    )
    fixed_now = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)
    cutoffs = service.get_retention_cutoffs(now=fixed_now)

    assert cutoffs["pipeline"] == fixed_now - timedelta(days=90)
    assert cutoffs["stage"] == fixed_now - timedelta(days=60)
    assert cutoffs["webhook"] == fixed_now - timedelta(days=30)
    assert cutoffs["evaluation"] == fixed_now - timedelta(days=90)


def test_storage_threshold_calculation_levels():
    # 1. NORMAL (< 70%)
    normal = calculate_storage_threshold_status(
        used_mb=100.0, max_mb=500.0, warning_pct=70.0, cleanup_pct=80.0, critical_pct=90.0
    )
    assert normal["status_level"] == "NORMAL"
    assert normal["percentage_used"] == 20.0

    # 2. WARNING (>= 70%)
    warning = calculate_storage_threshold_status(
        used_mb=360.0, max_mb=500.0, warning_pct=70.0, cleanup_pct=80.0, critical_pct=90.0
    )
    assert warning["status_level"] == "WARNING"
    assert warning["percentage_used"] == 72.0

    # 3. CLEANUP_RECOMMENDED (>= 80%)
    cleanup = calculate_storage_threshold_status(
        used_mb=410.0, max_mb=500.0, warning_pct=70.0, cleanup_pct=80.0, critical_pct=90.0
    )
    assert cleanup["status_level"] == "CLEANUP_RECOMMENDED"
    assert cleanup["percentage_used"] == 82.0

    # 4. CRITICAL (>= 90%)
    critical = calculate_storage_threshold_status(
        used_mb=460.0, max_mb=500.0, warning_pct=70.0, cleanup_pct=80.0, critical_pct=90.0
    )
    assert critical["status_level"] == "CRITICAL"
    assert critical["percentage_used"] == 92.0


def test_knowledge_protection_lists():
    # Check that knowledge tables are in PROTECTED_KNOWLEDGE_TABLES and NOT in ELIGIBLE_TELEMETRY_TABLES
    protected = {"issues", "comments", "pull_requests", "repositories", "issue_embeddings"}
    for t in protected:
        assert t in PROTECTED_KNOWLEDGE_TABLES
        assert t not in ELIGIBLE_TELEMETRY_TABLES


def test_dry_run_behavior_does_not_delete(in_memory_db):
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(days=120)

    # Populate old telemetry
    p_run = PipelineRun(
        pipeline_run_id="pipe_old_1",
        status="SUCCEEDED",
        created_at=old_time,
    )
    in_memory_db.add(p_run)
    in_memory_db.commit()

    service = RetentionService(pipeline_days=90)
    report = service.run_retention_housekeeping(in_memory_db, dry_run=True, now=now)

    assert report["dry_run"] is True
    assert report["eligible_records"]["pipeline_runs"] == 1
    assert report["deleted_records"]["pipeline_runs"] == 0

    # Verify database still retains record
    retained = in_memory_db.query(PipelineRun).filter_by(pipeline_run_id="pipe_old_1").first()
    assert retained is not None


def test_actual_cleanup_foreign_key_ordering_and_idempotency(in_memory_db):
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(days=120)

    # 1. Setup nested hierarchy: PipelineRun -> PipelineStageRun
    p_run = PipelineRun(
        pipeline_run_id="pipe_old_2",
        status="SUCCEEDED",
        created_at=old_time,
    )
    p_stage = PipelineStageRun(
        pipeline_run_id="pipe_old_2",
        stage_name="Stage 1",
        status="SUCCEEDED",
        started_at=old_time,
    )
    # 2. Setup ResolutionRun -> ResolutionClaimRecord -> VerificationRun
    r_run = ResolutionRun(
        id=1,
        run_id="res_old_2",
        model_name="gpt-4o-mini",
        prompt_version="v1",
        resolution_type="grounded",
        created_at=old_time,
    )
    v_run = VerificationRun(
        verification_run_id="ver_old_2",
        resolution_run_id=1,
        verifier_model="gpt-4o-mini",
        verifier_prompt_version="v1",
        overall_faithfulness_status="SUPPORTED",
        verified_at=old_time,
    )

    in_memory_db.add_all([p_run, p_stage, r_run, v_run])
    in_memory_db.commit()

    service = RetentionService(pipeline_days=90, stage_days=60)
    
    # First Execution (Actual Deletion)
    report1 = service.run_retention_housekeeping(in_memory_db, dry_run=False, now=now)
    assert report1["deleted_records"]["pipeline_runs"] == 1
    assert report1["deleted_records"]["resolution_runs"] == 1

    # Verify child & parent deleted cleanly
    assert in_memory_db.query(PipelineStageRun).filter_by(pipeline_run_id="pipe_old_2").first() is None
    assert in_memory_db.query(PipelineRun).filter_by(pipeline_run_id="pipe_old_2").first() is None

    # Idempotency Test (Second Execution should do nothing and exit gracefully)
    report2 = service.run_retention_housekeeping(in_memory_db, dry_run=False, now=now)
    assert sum(report2["eligible_records"].values()) == 0
    assert sum(report2["deleted_records"].values()) == 0


def test_knowledge_base_strictly_protected_during_cleanup(in_memory_db):
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(days=1000)  # Very old date

    # Add historical issue & embedding
    repo = Repository(id=1, full_name="StudySync/main", name="main", owner="StudySync")
    issue = Issue(
        id=101,
        github_issue_id=101,
        issue_number=101,
        repository_id=1,
        title="Study progress resets after page refresh",
        html_url="https://github.com/StudySync/main/issues/101",
        state="closed",
        created_at=old_time,
    )
    in_memory_db.add_all([repo, issue])
    in_memory_db.commit()

    service = RetentionService(pipeline_days=30)
    report = service.run_retention_housekeeping(in_memory_db, dry_run=False, now=now)

    # Verify historical issue remains in DB
    retained_issue = in_memory_db.query(Issue).filter_by(id=101).first()
    assert retained_issue is not None
    assert retained_issue.title == "Study progress resets after page refresh"
