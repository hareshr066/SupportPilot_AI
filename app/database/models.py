from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, JSON

# Global flag set during database initialization
HAS_PGVECTOR = False

class VectorOrJSON(TypeDecorator):
    """
    SQLAlchemy type decorator using pgvector.sqlalchemy.Vector(384) when pgvector
    extension is enabled in PostgreSQL, falling back to JSON array storage otherwise.
    """
    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = 384):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        global HAS_PGVECTOR
        if dialect.name == "postgresql" and HAS_PGVECTOR:
            try:
                from pgvector.sqlalchemy import Vector
                return dialect.type_descriptor(Vector(self.dim))
            except Exception:
                return dialect.type_descriptor(JSON)
        return dialect.type_descriptor(JSON)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------
# Association Tables for Many-to-Many Relationships
# ---------------------------------------------------------

issue_labels = Table(
    "issue_labels",
    Base.metadata,
    Column("issue_id", Integer, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True, index=True),
    Column("label_id", Integer, ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True, index=True),
)

issue_assignees = Table(
    "issue_assignees",
    Base.metadata,
    Column("issue_id", Integer, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True, index=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True),
)

issue_pull_requests = Table(
    "issue_pull_requests",
    Base.metadata,
    Column("issue_id", Integer, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True, index=True),
    Column("pull_request_id", Integer, ForeignKey("pull_requests.id", ondelete="CASCADE"), primary_key=True, index=True),
)


# ---------------------------------------------------------
# ORM Entity Models
# ---------------------------------------------------------

class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    github_repository_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    html_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    webhook_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_analysis_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    issues: Mapped[List["Issue"]] = relationship(
        "Issue", back_populates="repository", cascade="all, delete-orphan"
    )
    labels: Mapped[List["Label"]] = relationship(
        "Label", back_populates="repository", cascade="all, delete-orphan"
    )
    pull_requests: Mapped[List["PullRequest"]] = relationship(
        "PullRequest", back_populates="repository", cascade="all, delete-orphan"
    )


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    delivery_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    repository_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    processing_status: Mapped[str] = mapped_column(String(50), nullable=False, default="RECEIVED")  # RECEIVED, PROCESSING, PROCESSED, FAILED, IGNORED
    pipeline_run_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    repository: Mapped[Optional["Repository"]] = relationship("Repository")


class RepositorySyncRun(Base):
    __tablename__ = "repository_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_run_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    repository_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")  # PENDING, RUNNING, COMPLETED, FAILED, PARTIAL
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    issues_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pull_requests_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    repository: Mapped["Repository"] = relationship("Repository")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    github_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, unique=True)
    login: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    # Relationships
    authored_issues: Mapped[List["Issue"]] = relationship("Issue", back_populates="author")
    authored_comments: Mapped[List["Comment"]] = relationship("Comment", back_populates="author")
    assigned_issues: Mapped[List["Issue"]] = relationship(
        "Issue", secondary=issue_assignees, back_populates="assignees"
    )


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("repository_id", "name", name="uq_repository_label_name"),
    )

    # Relationships
    repository: Mapped["Repository"] = relationship("Repository", back_populates="labels")
    issues: Mapped[List["Issue"]] = relationship(
        "Issue", secondary=issue_labels, back_populates="labels"
    )


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    github_issue_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    repository_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    state_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    author_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    html_url: Mapped[str] = mapped_column(Text, nullable=False)
    duplicate_of_issue_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duplicate_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("repository_id", "issue_number", name="uq_repository_issue_number"),
        UniqueConstraint("repository_id", "github_issue_id", name="uq_repository_github_issue_id"),
    )

    # Relationships
    repository: Mapped["Repository"] = relationship("Repository", back_populates="issues")
    author: Mapped[Optional["User"]] = relationship("User", back_populates="authored_issues")
    labels: Mapped[List["Label"]] = relationship(
        "Label", secondary=issue_labels, back_populates="issues"
    )
    assignees: Mapped[List["User"]] = relationship(
        "User", secondary=issue_assignees, back_populates="assigned_issues"
    )
    comments: Mapped[List["Comment"]] = relationship(
        "Comment", back_populates="issue", cascade="all, delete-orphan"
    )
    pull_requests: Mapped[List["PullRequest"]] = relationship(
        "PullRequest", secondary=issue_pull_requests, back_populates="issues"
    )
    embeddings: Mapped[List["IssueEmbedding"]] = relationship(
        "IssueEmbedding", back_populates="issue", cascade="all, delete-orphan"
    )
    severity_predictions: Mapped[List["SeverityPrediction"]] = relationship(
        "SeverityPrediction", back_populates="issue", cascade="all, delete-orphan"
    )


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    github_comment_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, unique=True)
    issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    html_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="comments")
    author: Mapped[Optional["User"]] = relationship("User", back_populates="authored_comments")


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    github_pr_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    repository_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    html_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("repository_id", "pr_number", name="uq_repository_pr_number"),
    )

    # Relationships
    repository: Mapped["Repository"] = relationship("Repository", back_populates="pull_requests")
    issues: Mapped[List["Issue"]] = relationship(
        "Issue", secondary=issue_pull_requests, back_populates="pull_requests"
    )


class IssueEmbedding(Base):
    __tablename__ = "issue_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding = mapped_column(VectorOrJSON(384), nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("issue_id", "model_name", name="uq_issue_embedding_model"),
    )

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="embeddings")


class SeverityPrediction(Base):
    __tablename__ = "severity_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=True, index=True
    )
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    predicted_label: Mapped[str] = mapped_column(String(255), nullable=False)
    prediction_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    issue: Mapped[Optional["Issue"]] = relationship("Issue", back_populates="severity_predictions")


class RootCauseCluster(Base):
    __tablename__ = "root_cause_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    umap_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    hdbscan_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "cluster_id", name="uq_root_cause_run_cluster"),
    )

    # Relationships
    repository: Mapped["Repository"] = relationship("Repository")
    assignments: Mapped[List["RootCauseAssignment"]] = relationship(
        "RootCauseAssignment", back_populates="cluster", cascade="all, delete-orphan"
    )


class RootCauseAssignment(Base):
    __tablename__ = "root_cause_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_db_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("root_cause_clusters.id", ondelete="CASCADE"), nullable=True, index=True
    )
    run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    membership_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outlier_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "issue_id", name="uq_root_cause_run_issue"),
    )

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue")
    cluster: Mapped[Optional["RootCauseCluster"]] = relationship("RootCauseCluster", back_populates="assignments")


class RetrievalIndexMetadata(Base):
    __tablename__ = "retrieval_index_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    index_version: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    repository_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=True, index=True
    )
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    bm25_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    build_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    index_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class RetrievalEvaluationRun(Base):
    __tablename__ = "retrieval_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eval_run_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    repository_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=True, index=True
    )
    eval_query_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bm25_recall_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bm25_recall_10: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bm25_mrr_10: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dense_recall_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dense_recall_10: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dense_mrr_10: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hybrid_recall_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hybrid_recall_10: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hybrid_mrr_10: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hybrid_ndcg_10: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_info: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class ResolutionRun(Base):
    __tablename__ = "resolution_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    issue_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("issues.id", ondelete="SET NULL"), nullable=True, index=True
    )
    repository_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=True, index=True
    )
    retrieval_run_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(255), nullable=False)
    resolution_type: Mapped[str] = mapped_column(String(100), nullable=False)
    needs_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    citation_coverage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unsupported_claim_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    validation_status: Mapped[str] = mapped_column(String(100), nullable=False, default="passed")
    raw_output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    claims: Mapped[List["ResolutionClaimRecord"]] = relationship(
        "ResolutionClaimRecord", back_populates="run", cascade="all, delete-orphan"
    )


class ResolutionClaimRecord(Base):
    __tablename__ = "resolution_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(String(255), nullable=False)
    resolution_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resolution_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_ids: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    source_validation_status: Mapped[str] = mapped_column(String(100), nullable=False, default="valid")
    verification_status: Mapped[str] = mapped_column(String(100), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    run: Mapped["ResolutionRun"] = relationship("ResolutionRun", back_populates="claims")


class VerificationRun(Base):
    __tablename__ = "verification_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    verification_run_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    resolution_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resolution_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    verifier_model: Mapped[str] = mapped_column(String(255), nullable=False)
    verifier_prompt_version: Mapped[str] = mapped_column(String(255), nullable=False)
    overall_faithfulness_status: Mapped[str] = mapped_column(String(100), nullable=False)
    total_claims: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    partially_supported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unsupported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contradicted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unclear_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    citation_coverage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    claim_support_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    strict_faithfulness: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unsupported_claim_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    contradiction_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    needs_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    has_critical_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    claims: Mapped[List["ClaimVerificationRecord"]] = relationship(
        "ClaimVerificationRecord", back_populates="verification_run", cascade="all, delete-orphan"
    )


class ClaimVerificationRecord(Base):
    __tablename__ = "claim_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    verification_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("verification_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_id: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_claim_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_destructive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verdict: Mapped[str] = mapped_column(String(100), nullable=False)
    support_strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_ids: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    evidence_spans: Mapped[List[dict]] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    verification_run: Mapped["VerificationRun"] = relationship("VerificationRun", back_populates="claims")


class ConfidenceRun(Base):
    __tablename__ = "confidence_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    confidence_run_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("issues.id", ondelete="SET NULL"), nullable=True)
    resolution_run_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resolution_runs.id", ondelete="SET NULL"), nullable=True)
    verification_run_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("verification_runs.id", ondelete="SET NULL"), nullable=True)
    calibrated_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    decision: Mapped[str] = mapped_column(String(100), nullable=False)  # AUTO_RESOLVE, HUMAN_REVIEW, INSUFFICIENT_EVIDENCE, VERIFICATION_FAILED
    selected_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(100), nullable=False)
    threshold_version: Mapped[str] = mapped_column(String(100), nullable=False)
    features_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason_codes: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CalibrationRunRecord(Base):
    __tablename__ = "calibration_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    calibration_run_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    train_time_range: Mapped[str] = mapped_column(String(255), nullable=False)
    val_time_range: Mapped[str] = mapped_column(String(255), nullable=False)
    test_time_range: Mapped[str] = mapped_column(String(255), nullable=False)
    train_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    val_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    test_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    brier_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ece_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    selected_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.85)
    max_false_auto_resolution_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.02)
    auto_resolution_coverage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    false_auto_resolution_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CalibrationDatasetRecord(Base):
    __tablename__ = "calibration_dataset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    split: Mapped[str] = mapped_column(String(50), nullable=False)  # train, val, test
    features_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    correctness_label: Mapped[int] = mapped_column(Integer, nullable=False)  # 0 or 1
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RoutingTarget(Base):
    __tablename__ = "routing_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    routing_target_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    repository_id: Mapped[int] = mapped_column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    component: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    team: Mapped[str] = mapped_column(String(255), nullable=False)
    historical_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    repository: Mapped["Repository"] = relationship("Repository")


class RoutingPrediction(Base):
    __tablename__ = "routing_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    routing_prediction_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("issues.id", ondelete="SET NULL"), nullable=True)
    predicted_target: Mapped[str] = mapped_column(String(255), nullable=False)
    predicted_component: Mapped[str] = mapped_column(String(255), nullable=False)
    routing_probability: Mapped[float] = mapped_column(Float, nullable=False)
    top_k_targets: Mapped[List[dict]] = mapped_column(JSON, nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DecisionRun(Base):
    __tablename__ = "decision_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("issues.id", ondelete="SET NULL"), nullable=True)
    resolution_run_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resolution_runs.id", ondelete="SET NULL"), nullable=True)
    verification_run_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("verification_runs.id", ondelete="SET NULL"), nullable=True)
    confidence_run_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("confidence_runs.id", ondelete="SET NULL"), nullable=True)
    routing_prediction_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("routing_predictions.id", ondelete="SET NULL"), nullable=True)
    final_decision: Mapped[str] = mapped_column(String(100), nullable=False)  # AUTO_RESOLVE, ROUTE_TO_TEAM, HUMAN_REVIEW, ESCALATE_HIGH_RISK, INSUFFICIENT_EVIDENCE
    recommended_team: Mapped[str] = mapped_column(String(255), nullable=False)
    recommended_component: Mapped[str] = mapped_column(String(255), nullable=False)
    reason_codes: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    escalation_package_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("issues.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # RUNNING, SUCCEEDED, FAILED, ESCALATED
    final_decision: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    recommended_team: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    calibrated_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    routing_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    stage_runs: Mapped[List["PipelineStageRun"]] = relationship("PipelineStageRun", back_populates="pipeline_run", cascade="all, delete-orphan")


class PipelineStageRun(Base):
    __tablename__ = "pipeline_stage_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(String(255), ForeignKey("pipeline_runs.pipeline_run_id", ondelete="CASCADE"), nullable=False, index=True)
    stage_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # PENDING, RUNNING, SUCCEEDED, FAILED, SKIPPED
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_summary_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    pipeline_run: Mapped["PipelineRun"] = relationship("PipelineRun", back_populates="stage_runs")


class EvaluationRunRecord(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_run_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    code_version: Mapped[str] = mapped_column(String(100), nullable=False, default="v1.0.0")
    dataset_version: Mapped[str] = mapped_column(String(100), nullable=False, default="github_dataset_v1")
    feature_version: Mapped[str] = mapped_column(String(100), nullable=False, default="v1.0")
    model_versions_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="COMPLETED")  # COMPLETED, INSUFFICIENT_DATA, FAILED
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    metrics: Mapped[List["EvaluationMetricRecord"]] = relationship(
        "EvaluationMetricRecord", back_populates="evaluation_run", cascade="all, delete-orphan"
    )
    failures: Mapped[List["EvaluationFailureRecord"]] = relationship(
        "EvaluationFailureRecord", back_populates="evaluation_run", cascade="all, delete-orphan"
    )


class EvaluationMetricRecord(Base):
    __tablename__ = "evaluation_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_run_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("evaluation_runs.evaluation_run_id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # SEVERITY, DUPLICATE, ROOT_CAUSE, RETRIEVAL, RESOLUTION, FAITHFULNESS, CALIBRATION, ROUTING, END_TO_END
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    metric_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    evaluation_run: Mapped["EvaluationRunRecord"] = relationship("EvaluationRunRecord", back_populates="metrics")


class EvaluationFailureRecord(Base):
    __tablename__ = "evaluation_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_run_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("evaluation_runs.evaluation_run_id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticket_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    failed_stage: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    failure_category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    predicted_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ground_truth: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    evidence_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    evaluation_run: Mapped["EvaluationRunRecord"] = relationship("EvaluationRunRecord", back_populates="failures")








