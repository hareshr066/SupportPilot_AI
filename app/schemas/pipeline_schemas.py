from pydantic import BaseModel, Field, field_validator
from typing import TypedDict, List, Optional, Dict, Any


class TicketInput(BaseModel):
    ticket_id: Optional[int] = Field(None, description="Database issue ID if existing")
    repository_id: int = Field(1, description="Target repository DB ID")
    title: str = Field(..., description="Ticket title summary (required)")
    body: Optional[str] = Field("", description="Ticket body content")
    labels: List[str] = Field(default_factory=list, description="Existing GitHub labels")

    @field_validator("title")
    def validate_title_non_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Ticket title must not be empty.")
        return v.strip()


class PipelineGraphState(TypedDict, total=False):
    pipeline_run_id: str
    ticket_id: Optional[int]
    ticket_input: Dict[str, Any]
    severity_result: Optional[Dict[str, Any]]
    duplicate_result: Optional[Dict[str, Any]]
    root_cause_result: Optional[Dict[str, Any]]
    retrieval_result: Optional[Dict[str, Any]]
    resolution_result: Optional[Dict[str, Any]]
    verification_result: Optional[Dict[str, Any]]
    confidence_result: Optional[Dict[str, Any]]
    routing_result: Optional[Dict[str, Any]]
    decision_result: Optional[Dict[str, Any]]
    escalation_package: Optional[Dict[str, Any]]
    human_review_required: bool
    insufficient_evidence: bool
    stage_statuses: Dict[str, str]
    stage_latencies: Dict[str, float]
    errors: List[Dict[str, Any]]
    timestamps: Dict[str, str]


class PipelineResult(BaseModel):
    pipeline_run_id: str = Field(..., description="Unique pipeline execution ID")
    ticket_id: Optional[int] = Field(None, description="Ticket DB ID")
    status: str = Field(..., description="Pipeline execution status: SUCCEEDED, FAILED, ESCALATED")
    final_decision: str = Field(..., description="Final decision: AUTO_RESOLVE_RECOMMENDATION, HUMAN_ESCALATION, ROUTE_TO_TEAM")
    recommended_team: str = Field("GENERAL_SUPPORT_QUEUE", description="Target team assignment")
    calibrated_confidence: float = Field(0.0, description="Resolution calibrated confidence score")
    routing_probability: float = Field(0.0, description="Routing model confidence score")
    human_review_required: bool = Field(True, description="Whether human engineering review is required")
    total_latency_ms: float = Field(0.0, description="Total pipeline latency in milliseconds")
    stage_latencies: Dict[str, float] = Field(default_factory=dict, description="Per-stage latencies in milliseconds")
    stage_statuses: Dict[str, str] = Field(default_factory=dict, description="Status of each pipeline stage")
    severity: Optional[Dict[str, Any]] = Field(None, description="Severity prediction summary")
    duplicate: Optional[Dict[str, Any]] = Field(None, description="Duplicate detection summary")
    root_cause: Optional[Dict[str, Any]] = Field(None, description="Root cause cluster summary")
    retrieval: Optional[Dict[str, Any]] = Field(None, description="Retrieval summary")
    resolution: Optional[Dict[str, Any]] = Field(None, description="Grounded resolution summary")
    verification: Optional[Dict[str, Any]] = Field(None, description="Claim verification summary")
    confidence: Optional[Dict[str, Any]] = Field(None, description="Confidence prediction summary")
    routing: Optional[Dict[str, Any]] = Field(None, description="Routing prediction summary")
    decision: Optional[Dict[str, Any]] = Field(None, description="Final decision output summary")
    escalation_package: Optional[Dict[str, Any]] = Field(None, description="Structured human handoff package")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Errors encountered during pipeline execution")
    audit_reference: str = Field(..., description="Path/Reference to persisted audit trail artifact")
