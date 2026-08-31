from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class RoutingTargetInfo(BaseModel):
    routing_target_id: str = Field(..., description="Target routing identifier (e.g. component:terminal)")
    component: str = Field(..., description="Extracted component name")
    team: str = Field(..., description="Assigned team/owner group")
    historical_issue_count: int = Field(0, description="Historical issue count for component")


class TopKRoutingCandidate(BaseModel):
    component: str = Field(..., description="Target component name")
    team: str = Field(..., description="Assigned team name")
    probability: float = Field(..., ge=0.0, le=1.0, description="Scored probability or confidence")
    signal_source: str = Field("ml_model", description="Signal source: 'ml_model', 'baseline_retrieval', 'root_cause_purity', 'duplicate_match'")


class RoutingResult(BaseModel):
    routing_prediction_id: str = Field(..., description="Unique prediction run ID")
    ticket_id: Optional[int] = Field(None, description="Target ticket/issue ID")
    predicted_component: str = Field(..., description="Top predicted component")
    predicted_team: str = Field(..., description="Top predicted team/owner")
    routing_probability: float = Field(..., ge=0.0, le=1.0, description="Confidence in routing prediction")
    top_k: List[TopKRoutingCandidate] = Field(default_factory=list, description="Top K candidate components")
    is_low_support: bool = Field(False, description="True if component has < MIN_SAMPLES historical issues")
    is_unknown_target: bool = Field(False, description="True if component was unseen in training")
    model_version: str = Field(..., description="Routing model version string")


class HumanEscalationPackage(BaseModel):
    ticket_id: Optional[int] = Field(None, description="Ticket DB ID")
    ticket_title: str = Field("N/A", description="Ticket summary title")
    severity: str = Field("medium", description="Predicted severity level")
    is_duplicate: bool = Field(False, description="Whether issue is a duplicate")
    root_cause_candidate: str = Field("Unclustered", description="Root cause cluster name")
    retrieved_cases: List[Dict[str, Any]] = Field(default_factory=list, description="Top historical cases for context")
    generated_resolution: str = Field("", description="Generated resolution text")
    verification_verdict: str = Field("UNCLEAR", description="Verification summary status")
    unsupported_claims_count: int = Field(0, description="Number of unsupported claims")
    calibrated_confidence: float = Field(0.0, description="Empirical resolution confidence")
    suggested_component: str = Field("general", description="Suggested owner component")
    suggested_team: str = Field("GENERAL_SUPPORT_QUEUE", description="Suggested owner team")
    routing_probability: float = Field(0.0, description="Routing confidence probability")
    final_decision: str = Field("HUMAN_REVIEW", description="Final operational decision")
    reason_codes: List[str] = Field(default_factory=list, description="Reason codes for decision")
    recommended_human_action: str = Field("Review resolution and evidence before responding", description="Clear human next steps")


class FinalDecisionResult(BaseModel):
    decision_id: str = Field(..., description="Unique decision run ID")
    ticket_id: Optional[int] = Field(None, description="Target ticket ID")
    resolution_run_id: Optional[str] = Field(None, description="Associated resolution run ID")
    verification_run_id: Optional[str] = Field(None, description="Associated verification run ID")
    confidence_run_id: Optional[str] = Field(None, description="Associated confidence run ID")
    routing_prediction_id: Optional[str] = Field(None, description="Associated routing prediction ID")
    final_decision: str = Field(..., description="Final decision: AUTO_RESOLVE, ROUTE_TO_TEAM, HUMAN_REVIEW, ESCALATE_HIGH_RISK, INSUFFICIENT_EVIDENCE")
    recommended_team: str = Field(..., description="Assigned destination team")
    recommended_component: str = Field(..., description="Assigned destination component")
    calibrated_confidence: float = Field(0.0, description="Calibrated resolution confidence")
    routing_probability: float = Field(0.0, description="Routing confidence probability")
    reason_codes: List[str] = Field(default_factory=list, description="Controlled reason codes")
    escalation_package: HumanEscalationPackage = Field(..., description="Structured human handoff package")
