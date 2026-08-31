import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import select

from config import settings
from app.database.models import (
    Issue,
    ResolutionRun,
    VerificationRun,
    ConfidenceRun,
    RoutingPrediction,
    DecisionRun,
)
from app.schemas.verification_schemas import ResolutionVerificationSummary
from app.schemas.confidence_schemas import ConfidencePrediction
from app.schemas.routing_schemas import (
    RoutingResult,
    HumanEscalationPackage,
    FinalDecisionResult,
)

logger = logging.getLogger("decision_engine")

REASON_DESCRIPTIONS = {
    "ROUTING_HIGH_CONFIDENCE": "High confidence routing prediction to specialized component team",
    "ROUTING_LOW_CONFIDENCE": "Routing prediction confidence below minimum operational threshold",
    "NO_ROUTING_TARGET": "No valid routing target component identified",
    "CRITICAL_CLAIM_FAILURE": "Critical diagnosis or version claim failed independent verification",
    "CLAIM_CONTRADICTION": "Generated claim directly contradicts historical source evidence",
    "UNSUPPORTED_CRITICAL_CLAIM": "Critical claim lacks supporting evidence passages",
    "INSUFFICIENT_EVIDENCE": "Retrieved evidence completeness is insufficient for safe resolution",
    "CONFIDENCE_BELOW_THRESHOLD": "Calibrated resolution confidence is below auto-resolution threshold",
    "HIGH_CONFIDENCE_VERIFIED": "High calibrated confidence and fully verified claim evidence",
    "VERIFIER_UNAVAILABLE": "Independent claim verifier execution unavailable or failed",
    "LOW_EVIDENCE_COMPLETENESS": "Evidence completeness score below minimum budget",
    "DUPLICATE_CONFIRMED": "Ticket is a confirmed duplicate of an existing resolved issue",
    "DUPLICATE_UNCERTAIN": "Ticket has partial similarity to existing resolved issue",
    "HIGH_SEVERITY": "Ticket classified as high or critical severity",
    "UNKNOWN_ROUTING_TARGET": "Target component was unseen in historical training data",
    "LOW_SUPPORT_COMPONENT": "Target component has insufficient historical issue data",
}


def construct_human_escalation_package(
    ticket_id: Optional[int],
    ticket_title: str,
    severity: str,
    is_duplicate: bool,
    root_cause_candidate: str,
    retrieved_cases: List[Dict[str, Any]],
    resolution_text: str,
    verification_summary: Optional[ResolutionVerificationSummary],
    confidence_pred: Optional[ConfidencePrediction],
    routing_res: Optional[RoutingResult],
    final_decision: str,
    reason_codes: List[str]
) -> HumanEscalationPackage:
    """
    Constructs a complete, structured human handoff package for support engineers.
    Prevents engineers from needing to repeat technical investigation.
    """
    ver_verdict = verification_summary.overall_faithfulness_status if verification_summary else "UNCLEAR"
    unsup_cnt = verification_summary.unsupported_count if verification_summary else 1
    conf_val = confidence_pred.calibrated_confidence if confidence_pred else 0.0

    sugg_comp = routing_res.predicted_component if routing_res else "general"
    sugg_team = routing_res.predicted_team if routing_res else settings.routing_default_queue
    rout_prob = routing_res.routing_probability if routing_res else 0.0

    # Determine recommended human action
    if final_decision == "AUTO_RESOLVE":
        rec_action = "Review recommended resolution and confirm automated response."
    elif final_decision == "ESCALATE_HIGH_RISK" or "CRITICAL_CLAIM_FAILURE" in reason_codes:
        rec_action = "URGENT: Review unsupported critical claim and perform manual verification before responding."
    elif final_decision == "INSUFFICIENT_EVIDENCE":
        rec_action = "Request additional diagnostic logs or repro steps from ticket author."
    elif final_decision == "ROUTE_TO_TEAM":
        rec_action = f"Assign ticket to {sugg_team} for domain-specific investigation."
    else:
        rec_action = "Review retrieved evidence, verify resolution steps, and post manual response."

    return HumanEscalationPackage(
        ticket_id=ticket_id,
        ticket_title=ticket_title,
        severity=severity,
        is_duplicate=is_duplicate,
        root_cause_candidate=root_cause_candidate,
        retrieved_cases=retrieved_cases[:3],
        generated_resolution=resolution_text,
        verification_verdict=ver_verdict,
        unsupported_claims_count=unsup_cnt,
        calibrated_confidence=conf_val,
        suggested_component=sugg_comp,
        suggested_team=sugg_team,
        routing_probability=rout_prob,
        final_decision=final_decision,
        reason_codes=reason_codes,
        recommended_human_action=rec_action
    )


class DeterministicDecisionEngine:
    """
    Deterministic Operational Escalation & Routing Decision Engine.
    Executes explicit policy precedence to determine operational decision without LLM calls.
    """

    def make_final_decision(
        self,
        ticket_id: Optional[int] = None,
        ticket_title: str = "Support Ticket",
        severity_level: str = "medium",
        is_duplicate: bool = False,
        root_cause_cluster: str = "Unclustered",
        retrieved_cases: Optional[List[Dict[str, Any]]] = None,
        resolution_data: Optional[Dict[str, Any]] = None,
        verification_summary: Optional[ResolutionVerificationSummary] = None,
        confidence_pred: Optional[ConfidencePrediction] = None,
        routing_res: Optional[RoutingResult] = None,
        session: Optional[Session] = None
    ) -> FinalDecisionResult:
        """
        Executes strict decision hierarchy precedence across all pipeline signals.
        """
        reason_codes: List[str] = []
        ret_cases = retrieved_cases or []
        res_text = resolution_data.get("summary", "") if resolution_data else ""

        # Collect reason codes from routing
        if routing_res:
            if routing_res.is_unknown_target:
                reason_codes.append("UNKNOWN_ROUTING_TARGET")
            elif routing_res.is_low_support:
                reason_codes.append("LOW_SUPPORT_COMPONENT")
            elif routing_res.routing_probability >= settings.routing_min_confidence:
                reason_codes.append("ROUTING_HIGH_CONFIDENCE")
            else:
                reason_codes.append("ROUTING_LOW_CONFIDENCE")

        # Collect severity / duplicate signals
        if severity_level.lower() in ["high", "critical"]:
            reason_codes.append("HIGH_SEVERITY")
        if is_duplicate:
            reason_codes.append("DUPLICATE_CONFIRMED")

        # Decision Hierarchy Precedence
        final_decision = "HUMAN_REVIEW"

        # 1. Verification Failures & Contradictions
        if verification_summary is None:
            final_decision = "HUMAN_REVIEW"
            reason_codes.append("VERIFIER_UNAVAILABLE")
        elif verification_summary.has_critical_failure:
            if severity_level.lower() in ["high", "critical"]:
                final_decision = "ESCALATE_HIGH_RISK"
            else:
                final_decision = "HUMAN_REVIEW"
            reason_codes.append("CRITICAL_CLAIM_FAILURE")
            reason_codes.append("UNSUPPORTED_CRITICAL_CLAIM")
        elif verification_summary.contradicted_count > 0:
            final_decision = "ESCALATE_HIGH_RISK"
            reason_codes.append("CLAIM_CONTRADICTION")

        # 2. Insufficient Evidence
        elif not ret_cases or (resolution_data and resolution_data.get("evidence_completeness", 0.0) < 0.35):
            final_decision = "INSUFFICIENT_EVIDENCE"
            reason_codes.append("LOW_EVIDENCE_COMPLETENESS")
            reason_codes.append("INSUFFICIENT_EVIDENCE")

        # 3. Confidence Below Threshold
        elif confidence_pred is None or confidence_pred.calibrated_confidence < confidence_pred.threshold:
            final_decision = "HUMAN_REVIEW"
            reason_codes.append("CONFIDENCE_BELOW_THRESHOLD")

        # 4. Low Routing Confidence or Unknown Team
        elif routing_res is None or routing_res.routing_probability < settings.routing_min_confidence or routing_res.is_unknown_target:
            final_decision = "ROUTE_TO_TEAM"
            reason_codes.append("ROUTING_LOW_CONFIDENCE")

        # 5. AUTO_RESOLVE Eligibility (All safety checks passed!)
        elif (
            confidence_pred.calibrated_confidence >= confidence_pred.threshold
            and verification_summary.overall_faithfulness_status in ["FULLY_SUPPORTED", "MOSTLY_SUPPORTED"]
            and not verification_summary.has_critical_failure
            and verification_summary.contradicted_count == 0
        ):
            final_decision = "AUTO_RESOLVE"
            reason_codes.append("HIGH_CONFIDENCE_VERIFIED")

        else:
            final_decision = "HUMAN_REVIEW"

        # Determine Recommended Team / Component
        if routing_res:
            rec_comp = routing_res.predicted_component
            rec_team = routing_res.predicted_team
        else:
            rec_comp = "general"
            rec_team = settings.routing_default_queue

        # Construct Escalation Package
        esc_package = construct_human_escalation_package(
            ticket_id=ticket_id,
            ticket_title=ticket_title,
            severity=severity_level,
            is_duplicate=is_duplicate,
            root_cause_candidate=root_cause_cluster,
            retrieved_cases=ret_cases,
            resolution_text=res_text,
            verification_summary=verification_summary,
            confidence_pred=confidence_pred,
            routing_res=routing_res,
            final_decision=final_decision,
            reason_codes=list(set(reason_codes))
        )

        now_utc = datetime.now(timezone.utc)
        dec_id = f"dec_{now_utc.strftime('%Y%m%d_%H%M%S_%f')[:20]}"

        res_obj = FinalDecisionResult(
            decision_id=dec_id,
            ticket_id=ticket_id,
            resolution_run_id=verification_summary.resolution_run_id if verification_summary else None,
            verification_run_id=verification_summary.verification_run_id if verification_summary else None,
            confidence_run_id=confidence_pred.confidence_run_id if confidence_pred else None,
            routing_prediction_id=routing_res.routing_prediction_id if routing_res else None,
            final_decision=final_decision,
            recommended_team=rec_team,
            recommended_component=rec_comp,
            calibrated_confidence=confidence_pred.calibrated_confidence if confidence_pred else 0.0,
            routing_probability=routing_res.routing_probability if routing_res else 0.0,
            reason_codes=list(set(reason_codes)),
            escalation_package=esc_package
        )

        # DB Persistence
        if session is not None:
            db_rec = DecisionRun(
                decision_id=dec_id,
                ticket_id=ticket_id,
                resolution_run_id=None,
                verification_run_id=None,
                confidence_run_id=None,
                routing_prediction_id=None,
                final_decision=final_decision,
                recommended_team=rec_team,
                recommended_component=rec_comp,
                reason_codes=res_obj.reason_codes,
                escalation_package_json=esc_package.model_dump(),
                created_at=now_utc
            )
            session.add(db_rec)
            session.commit()

        # Audit Trail Artifacts
        artifact_dir = Path("artifacts/decision") / f"run_{dec_id}"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        with open(artifact_dir / "decision.json", "w", encoding="utf-8") as f:
            json.dump(res_obj.model_dump(), f, indent=2)

        with open(artifact_dir / "human_review_package.json", "w", encoding="utf-8") as f:
            json.dump(esc_package.model_dump(), f, indent=2)

        with open(artifact_dir / "audit_trail.json", "w", encoding="utf-8") as f:
            json.dump({
                "decision_id": dec_id,
                "ticket_id": ticket_id,
                "resolution_run_id": res_obj.resolution_run_id,
                "verification_run_id": res_obj.verification_run_id,
                "confidence_run_id": res_obj.confidence_run_id,
                "routing_prediction_id": res_obj.routing_prediction_id,
                "final_decision": final_decision,
                "reason_codes": res_obj.reason_codes
            }, f, indent=2)

        logger.info(f"Final Decision computed: {dec_id} -> {final_decision} ({rec_team})")
        return res_obj


def render_human_readable_decision(res: FinalDecisionResult) -> str:
    """Renders formatted human-readable decision & escalation report."""
    lines = []
    lines.append("===================================================================================")
    lines.append("                SUPPORTPILOT FINAL DECISION & ESCALATION REPORT                    ")
    lines.append("===================================================================================")
    lines.append(f"DECISION ID:         {res.decision_id}")
    lines.append(f"TICKET ID:           {res.ticket_id or 'N/A'}")
    lines.append(f"FINAL DECISION:      {res.final_decision}")
    lines.append(f"RECOMMENDED TEAM:    {res.recommended_team}")
    lines.append(f"RECOMMENDED COMP:    {res.recommended_component}")
    lines.append(f"CALIBRATED CONF:     {res.calibrated_confidence * 100:.2f}%")
    lines.append(f"ROUTING CONF:        {res.routing_probability * 100:.2f}%")
    lines.append("-----------------------------------------------------------------------------------")
    lines.append("REASON CODES:")
    for code in res.reason_codes:
        desc = REASON_DESCRIPTIONS.get(code, "")
        lines.append(f"  - [{code}] {desc}")
    lines.append("-----------------------------------------------------------------------------------")
    lines.append("HUMAN ESCALATION HANDOFF PACKAGE:")
    pkg = res.escalation_package
    lines.append(f"  Ticket Title:       {pkg.ticket_title}")
    lines.append(f"  Severity Level:     {pkg.severity.upper()}")
    lines.append(f"  Duplicate Status:   {'Confirmed Duplicate' if pkg.is_duplicate else 'Unique Issue'}")
    lines.append(f"  Root Cause Cluster: {pkg.root_cause_candidate}")
    lines.append(f"  Verification Status:{pkg.verification_verdict} ({pkg.unsupported_claims_count} unsupported claims)")
    lines.append(f"  Human Action:       {pkg.recommended_human_action}")
    lines.append("===================================================================================\n")
    return "\n".join(lines)
