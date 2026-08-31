from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


# =====================================================================
# REQUEST SCHEMAS
# =====================================================================

class TicketAnalyzeRequest(BaseModel):
    repository_id: Any = Field(
        ...,
        description="Repository identifier or database integer ID",
        json_schema_extra={"example": 1}
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Support ticket or issue title (non-empty)",
        json_schema_extra={"example": "Integrated terminal pty crash on Windows"}
    )
    body: Optional[str] = Field(
        "",
        description="Detailed description or stack trace of the support ticket",
        json_schema_extra={"example": "PowerShell terminal exits immediately with exit code 1."}
    )
    issue_number: Optional[int] = Field(
        None,
        description="Optional original GitHub issue number",
        json_schema_extra={"example": 1042}
    )

    @field_validator("title")
    @classmethod
    def validate_title_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Ticket title must not be empty or whitespace only.")
        return v.strip()


# =====================================================================
# ERROR RESPONSE SCHEMAS
# =====================================================================

class APIErrorDetail(BaseModel):
    code: str = Field(..., description="Controlled error code string")
    message: str = Field(..., description="Human-readable error description")
    request_id: Optional[str] = Field(None, description="Unique request tracing ID")


class APIErrorResponse(BaseModel):
    error: APIErrorDetail


# =====================================================================
# HEALTH & READINESS RESPONSE SCHEMAS
# =====================================================================

class HealthResponse(BaseModel):
    status: str = Field("ok", description="Service operational status")
    service: str = Field("supportpilot", description="Service name")


class ReadinessResponse(BaseModel):
    status: str = Field(..., description="Readiness status ('ready' or 'not_ready')")
    checks: Dict[str, str] = Field(..., description="Individual dependency health checks")


# =====================================================================
# PIPELINE STATUS & STAGE SCHEMAS
# =====================================================================

class PipelineRunSummaryResponse(BaseModel):
    pipeline_run_id: str
    ticket_id: Optional[int] = None
    status: str
    final_decision: str
    recommended_team: Optional[str] = None
    calibrated_confidence: float = 0.0
    routing_probability: float = 0.0
    total_latency_ms: float = 0.0
    created_at: Optional[str] = None


class PipelineStageRunResponse(BaseModel):
    stage: str
    status: str
    latency_ms: float = 0.0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


# =====================================================================
# EVIDENCE & ESCALATION RESPONSE SCHEMAS
# =====================================================================

class EvidenceReferenceItem(BaseModel):
    issue_id: int
    issue_number: Optional[int] = None
    title: str
    html_url: Optional[str] = None
    dense_similarity: float = 0.0
    bm25_score: float = 0.0
    rrf_score: float = 0.0
    evidence_text_snippet: str = ""


class EvidenceSummaryResponse(BaseModel):
    pipeline_run_id: str
    ticket_id: Optional[int] = None
    evidence_completeness: float = 0.0
    num_retrieved_cases: int = 0
    retrieved_cases: List[EvidenceReferenceItem] = Field(default_factory=list)
    verification_summary: Optional[Dict[str, Any]] = None


class EscalationPackageResponse(BaseModel):
    pipeline_run_id: str
    ticket_id: Optional[int] = None
    escalated: bool = True
    reason_codes: List[str] = Field(default_factory=list)
    suggested_team: Optional[str] = None
    suggested_component: Optional[str] = None
    escalation_package: Dict[str, Any] = Field(default_factory=dict)


# =====================================================================
# REPOSITORY, SYNC & WEBHOOK SCHEMAS
# =====================================================================

class CreateRepositoryRequest(BaseModel):
    owner: str = Field(..., min_length=1, description="GitHub repository owner/organization")
    name: str = Field(..., min_length=1, description="GitHub repository name")

    @field_validator("owner", "name")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field must not be empty or whitespace only.")
        return v.strip()


class RepositoryResponse(BaseModel):
    id: int
    github_repository_id: Optional[int] = None
    owner: str
    name: str
    full_name: str
    html_url: Optional[str] = None
    enabled: bool = True
    webhook_enabled: bool = True
    auto_analysis_enabled: bool = True
    last_synced_at: Optional[str] = None
    issue_count: int = 0
    created_at: Optional[str] = None


class SyncRepositoryRequest(BaseModel):
    max_issues: Optional[int] = Field(None, description="Optional maximum issues to synchronize")


class SyncResponse(BaseModel):
    sync_run_id: str
    repository_id: int
    status: str
    started_at: str


class SyncStatusResponse(BaseModel):
    sync_run_id: str
    repository_id: int
    status: str
    started_at: str
    completed_at: Optional[str] = None
    issues_processed: int = 0
    comments_processed: int = 0
    pull_requests_processed: int = 0
    error_summary: Optional[str] = None


class WebhookResponse(BaseModel):
    delivery_id: str
    status: str
    event_type: str
    action: Optional[str] = None
    pipeline_run_id: Optional[str] = None
