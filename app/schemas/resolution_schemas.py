from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Union


class ResolutionRequest(BaseModel):
    title: str = Field(..., description="Title of the incoming support ticket")
    body: str = Field("", description="Detailed body text of the ticket")
    repository_id: Optional[int] = Field(None, description="Database ID of the repository")
    issue_number: Optional[int] = Field(None, description="GitHub issue number if existing ticket")
    severity_prediction: Optional[str] = Field(None, description="Model-derived severity prediction")
    root_cause_cluster: Optional[str] = Field(None, description="Model-derived root cause cluster label")
    environment: Optional[str] = Field(None, description="User environment details")
    version: Optional[str] = Field(None, description="Software version details")
    platform: Optional[str] = Field(None, description="OS or platform details")


class EvidenceCase(BaseModel):
    case_id: str = Field(..., description="Stable source identifier (e.g. issue:123)")
    issue_number: int = Field(..., description="GitHub issue number")
    repository: str = Field(..., description="Full repository owner/name")
    title: str = Field(..., description="Title of historical issue")
    problem_snippet: str = Field("", description="Concise body/problem snippet")
    resolution_snippet: str = Field("", description="Concise resolution snippet")
    pull_requests: List[Dict[str, Any]] = Field(default_factory=list, description="Linked pull requests")
    source_urls: List[str] = Field(default_factory=list, description="Canonical source URLs")
    retrieval_score: float = Field(0.0, description="Final RRF hybrid retrieval score")
    evidence_completeness: float = Field(0.0, description="Completeness indicator 0.0-1.0")


class EvidencePackage(BaseModel):
    query_ticket: Dict[str, Any] = Field(..., description="Query ticket metadata")
    cases: List[EvidenceCase] = Field(default_factory=list, description="Selected evidence cases")
    total_cases: int = Field(0, description="Total number of evidence cases included")
    truncated: bool = Field(False, description="Whether evidence context was truncated")


class ResolutionStep(BaseModel):
    step: int = Field(1, description="1-indexed step sequence number")
    instruction: str = Field("", description="Step instruction text")
    source_ids: List[str] = Field(default_factory=list, description="Source case IDs supporting step")

    @field_validator("step", mode="before")
    def validate_step(cls, v, info):
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            if v.isdigit():
                return int(v)
            # If the LLM put the instruction into 'step'
            return 1
        return 1

    @field_validator("instruction", mode="before")
    def validate_instruction(cls, v, info):
        if isinstance(v, str) and v.strip():
            return v.strip()
        # Fallback if instruction was empty but step was a string text
        raw_step = info.data.get("step") if hasattr(info, "data") else None
        if isinstance(raw_step, str) and not raw_step.isdigit():
            return raw_step.strip()
        return str(v) if v is not None else ""

    @field_validator("source_ids", mode="before")
    def validate_step_sources(cls, v):
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        if isinstance(v, list):
            return [str(x).strip() for x in v if x]
        return []


class ResolutionClaim(BaseModel):
    claim_id: str = Field("c1", description="Atomic claim identifier (e.g. c1)")
    text: str = Field(..., description="Atomic factual claim text")
    source_ids: List[str] = Field(default_factory=list, description="Cited source case IDs")
    source_validation_status: Optional[str] = Field("valid", description="Status after checking source ID presence")
    verification_status: str = Field("pending", description="Claim verification status")

    @field_validator("source_ids", mode="before")
    def validate_claim_sources(cls, v):
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        if isinstance(v, list):
            return [str(x).strip() for x in v if x]
        return []


class ResolutionResponse(BaseModel):
    summary: str = Field(..., description="Executive summary of the resolution")
    diagnosis: str = Field(..., description="Root cause diagnosis based on evidence")
    recommended_resolution: str = Field(..., description="Full recommended resolution action")
    resolution_type: str = Field(
        ...,
        description="Type: 'confirmed_historical_resolution', 'evidence_based_recommendation', 'insufficient_evidence'"
    )
    steps: List[ResolutionStep] = Field(default_factory=list, description="Ordered resolution steps")
    claims: List[ResolutionClaim] = Field(default_factory=list, description="Atomic claims with source citations")
    limitations: List[str] = Field(default_factory=list, description="Known resolution limitations/uncertainties")
    needs_human_review: bool = Field(True, description="Flag indicating human triage review required")
    citation_coverage: float = Field(0.0, description="Percentage of claims containing valid source IDs")
    unsupported_claim_rate: float = Field(0.0, description="Percentage of claims with unsupported/missing source IDs")
