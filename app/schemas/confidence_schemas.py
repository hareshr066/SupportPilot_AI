from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ConfidenceFeatureVector(BaseModel):
    # A. Retrieval Strength
    top_dense_similarity: float = Field(0.0, description="Top candidate dense similarity score")
    top_bm25_score: float = Field(0.0, description="Top candidate BM25 score")
    top_rrf_score: float = Field(0.0, description="Top candidate Reciprocal Rank Fusion score")
    retrieval_score_gap: float = Field(0.0, description="Score difference between #1 and #2 candidate")

    # B. Evidence Quality
    evidence_completeness: float = Field(0.0, description="Completeness indicator 0.0 to 1.0")
    num_retrieved_cases: int = Field(0, description="Number of retrieved historical cases")
    num_usable_sources: int = Field(0, description="Number of valid source documents available")

    # C. Claim Verification Signals
    supported_claim_ratio: float = Field(0.0, description="Ratio of SUPPORTED claims")
    partial_claim_ratio: float = Field(0.0, description="Ratio of PARTIALLY_SUPPORTED claims")
    unsupported_claim_ratio: float = Field(0.0, description="Ratio of UNSUPPORTED claims")
    contradiction_ratio: float = Field(0.0, description="Ratio of CONTRADICTED claims")
    citation_coverage: float = Field(0.0, description="Percentage of valid source citations")
    critical_unsupported_count: int = Field(0, description="Number of critical unsupported claims")
    critical_contradiction_count: int = Field(0, description="Number of critical contradicted claims")

    # D. Resolution Properties
    num_factual_claims: int = Field(0, description="Total number of claims")
    num_steps: int = Field(0, description="Total number of resolution steps")

    # E. Duplicate Signal
    duplicate_probability: float = Field(0.0, description="Duplicate detector probability")
    strong_historical_match_exists: int = Field(0, description="1 if duplicate match >= 0.85 else 0")

    # F. Severity Signal
    severity_confidence: float = Field(0.0, description="Severity classifier probability")

    def to_list(self) -> List[float]:
        """Converts feature vector to ordered float list for ML model input."""
        return [
            self.top_dense_similarity,
            self.top_bm25_score,
            self.top_rrf_score,
            self.retrieval_score_gap,
            self.evidence_completeness,
            float(self.num_retrieved_cases),
            float(self.num_usable_sources),
            self.supported_claim_ratio,
            self.partial_claim_ratio,
            self.unsupported_claim_ratio,
            self.contradiction_ratio,
            self.citation_coverage,
            float(self.critical_unsupported_count),
            float(self.critical_contradiction_count),
            float(self.num_factual_claims),
            float(self.num_steps),
            self.duplicate_probability,
            float(self.strong_historical_match_exists),
            self.severity_confidence,
        ]

    @classmethod
    def feature_names(cls) -> List[str]:
        return [
            "top_dense_similarity", "top_bm25_score", "top_rrf_score", "retrieval_score_gap",
            "evidence_completeness", "num_retrieved_cases", "num_usable_sources",
            "supported_claim_ratio", "partial_claim_ratio", "unsupported_claim_ratio",
            "contradiction_ratio", "citation_coverage", "critical_unsupported_count",
            "critical_contradiction_count", "num_factual_claims", "num_steps",
            "duplicate_probability", "strong_historical_match_exists", "severity_confidence"
        ]


class ConfidencePrediction(BaseModel):
    confidence_run_id: str = Field(..., description="Unique run ID")
    ticket_id: Optional[int] = Field(None, description="Target issue/ticket ID")
    resolution_run_id: Optional[str] = Field(None, description="Resolution run ID")
    calibrated_confidence: float = Field(..., ge=0.0, le=1.0, description="Empirically calibrated confidence score P(correct | features)")
    decision: str = Field(..., description="Decision: 'AUTO_RESOLVE', 'HUMAN_REVIEW', 'INSUFFICIENT_EVIDENCE', 'VERIFICATION_FAILED'")
    threshold: float = Field(..., description="Selected confidence threshold under false-positive budget")
    reason_codes: List[str] = Field(default_factory=list, description="Controlled reason codes explaining decision")
    model_version: str = Field(..., description="Calibration model version")
    feature_version: str = Field(..., description="Feature vector version")
    threshold_version: str = Field(..., description="Threshold configuration version")
    features: ConfidenceFeatureVector = Field(..., description="Extracted input feature vector")


class CalibrationMetrics(BaseModel):
    brier_score: float = Field(0.0, description="Brier score mean((p_i - y_i)^2)")
    ece: float = Field(0.0, description="Expected Calibration Error across bins")
    mce: float = Field(0.0, description="Maximum Calibration Error across bins")
    selected_threshold: float = Field(0.85, description="Selected threshold meeting false-positive budget")
    max_false_auto_resolution_rate: float = Field(0.02, description="Target false auto-resolution rate budget")
    auto_resolution_coverage: float = Field(0.0, description="Fraction of tickets automatically resolved")
    false_auto_resolution_rate: float = Field(0.0, description="Error rate among auto-resolved tickets")
