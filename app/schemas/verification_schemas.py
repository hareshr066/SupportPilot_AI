from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class EvidenceSpan(BaseModel):
    source_id: str = Field(..., description="Stable source identifier (e.g., issue:123 or pr:456)")
    text: str = Field(..., description="Exact or excerpt passage extracted from source evidence")
    relevance_score: float = Field(0.0, description="Relevance score of snippet to the claim")


class LLMVerifierOutput(BaseModel):
    verdict: str = Field("UNCLEAR", description="Verdict: SUPPORTED, PARTIALLY_SUPPORTED, UNSUPPORTED, CONTRADICTED, UNCLEAR")
    support_strength: float = Field(0.0, ge=0.0, le=1.0, description="Support strength score 0.0 to 1.0")
    explanation: str = Field("", description="Verification explanation")
    evidence_spans: List[EvidenceSpan] = Field(default_factory=list, description="Extracted evidence spans")


class ClaimVerificationResult(BaseModel):
    claim_id: str = Field(..., description="Atomic claim identifier (e.g. c1 or c1_a)")
    parent_claim_id: Optional[str] = Field(None, description="Parent claim ID if claim was decomposed")
    claim_text: str = Field(..., description="Atomic factual claim text being verified")
    verdict: str = Field(
        ...,
        description="Verdict: 'SUPPORTED', 'PARTIALLY_SUPPORTED', 'UNSUPPORTED', 'CONTRADICTED', 'UNCLEAR'"
    )
    support_strength: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Evidence strength score (0.0 to 1.0). Note: support_strength != calibrated probability."
    )
    evidence_spans: List[EvidenceSpan] = Field(default_factory=list, description="Extracted source passages supporting verdict")
    source_ids: List[str] = Field(default_factory=list, description="Source IDs evaluated")
    explanation: str = Field("", description="Verifier rationale explaining the verdict")
    is_critical: bool = Field(False, description="Whether claim is classified as critical (diagnosis, fix, version)")
    is_destructive: bool = Field(False, description="Whether claim involves destructive actions (delete, migration, security)")
    verifier_model: str = Field(..., description="Model identifier used for verification")
    verifier_prompt_version: str = Field(..., description="Version of the verifier prompt")


class ResolutionVerificationSummary(BaseModel):
    verification_run_id: str = Field(..., description="Unique run ID for this verification run")
    resolution_run_id: str = Field(..., description="ID of the target resolution run")
    overall_faithfulness_status: str = Field(
        ...,
        description="Resolution status: 'FULLY_SUPPORTED', 'MOSTLY_SUPPORTED', 'PARTIALLY_SUPPORTED', 'UNSUPPORTED', 'CONTRADICTED', 'NEEDS_HUMAN_REVIEW'"
    )
    total_claims: int = Field(0, description="Total number of factual claims evaluated")
    supported_count: int = Field(0, description="Number of SUPPORTED claims")
    partially_supported_count: int = Field(0, description="Number of PARTIALLY_SUPPORTED claims")
    unsupported_count: int = Field(0, description="Number of UNSUPPORTED claims")
    contradicted_count: int = Field(0, description="Number of CONTRADICTED claims")
    unclear_count: int = Field(0, description="Number of UNCLEAR claims")
    citation_coverage: float = Field(0.0, description="Percentage of claims citing valid source IDs")
    claim_support_rate: float = Field(0.0, description="Ratio of SUPPORTED claims to total claims")
    strict_faithfulness: float = Field(0.0, description="Ratio of strictly SUPPORTED claims (partial not counted as full)")
    unsupported_claim_rate: float = Field(0.0, description="Ratio of UNSUPPORTED claims to total claims")
    contradiction_rate: float = Field(0.0, description="Ratio of CONTRADICTED claims to total claims")
    partial_support_rate: float = Field(0.0, description="Ratio of PARTIALLY_SUPPORTED claims to total claims")
    needs_human_review: bool = Field(True, description="Flag indicating human review required")
    has_critical_failure: bool = Field(False, description="True if any critical/destructive claim is unsupported/contradicted")
    claim_results: List[ClaimVerificationResult] = Field(default_factory=list, description="Detailed per-claim results")
