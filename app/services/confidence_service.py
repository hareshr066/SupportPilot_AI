import os
import csv
import json
import time
import joblib
import logging
import numpy as np
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
    ClaimVerificationRecord,
    ConfidenceRun,
    CalibrationRunRecord,
    CalibrationDatasetRecord,
)
from app.schemas.verification_schemas import ResolutionVerificationSummary
from app.schemas.confidence_schemas import (
    ConfidenceFeatureVector,
    ConfidencePrediction,
    CalibrationMetrics,
)

logger = logging.getLogger("confidence_calibration")

# Controlled Reason Codes Vocabulary
REASON_CODES = {
    "HIGH_RETRIEVAL_SUPPORT": "High retrieval similarity and hybrid score",
    "LOW_RETRIEVAL_SUPPORT": "Low retrieval similarity score across candidates",
    "HIGH_EVIDENCE_COMPLETENESS": "High historical resolution evidence completeness",
    "LOW_EVIDENCE_COMPLETENESS": "Low evidence completeness in retrieved sources",
    "ALL_CLAIMS_SUPPORTED": "All generated factual claims are explicitly supported by evidence",
    "UNSUPPORTED_CLAIMS_PRESENT": "One or more factual claims lack evidence support",
    "CONTRADICTION_PRESENT": "One or more factual claims contradict historical evidence",
    "CRITICAL_CLAIM_FAILURE": "Critical diagnosis or fix claim failed verification",
    "CONFIDENCE_BELOW_THRESHOLD": "Calibrated confidence is below auto-resolution threshold",
    "CALIBRATED_CONFIDENCE_ABOVE_THRESHOLD": "Calibrated confidence satisfies false-positive budget threshold",
    "CALIBRATION_MODEL_UNAVAILABLE": "Calibration model not found; using fallback evaluation",
    "VERIFIER_UNAVAILABLE": "Verification summary unavailable or failed",
}


def calculate_brier_score(y_true: List[int], probabilities: List[float]) -> float:
    """
    Calculates Brier Score: mean((p_i - y_i)^2).
    Lower is better (0.0 is perfect calibration).
    """
    y_arr = np.array(y_true, dtype=float)
    p_arr = np.array(probabilities, dtype=float)
    if len(y_arr) == 0 or len(y_arr) != len(p_arr):
        return 0.0
    p_clamped = np.clip(p_arr, 0.0, 1.0)
    return float(np.mean((p_clamped - y_arr) ** 2))


def calculate_ece(
    y_true: List[int],
    probabilities: List[float],
    n_bins: int = 10
) -> Tuple[float, float, List[Dict[str, Any]]]:
    """
    Calculates Expected Calibration Error (ECE) and Maximum Calibration Error (MCE).
    Returns (ece, mce, bin_table).
    """
    y_arr = np.array(y_true, dtype=int)
    p_arr = np.clip(np.array(probabilities, dtype=float), 0.0, 1.0)
    N = len(y_arr)

    if N == 0:
        return 0.0, 0.0, []

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_table = []
    total_ece = 0.0
    max_ce = 0.0

    for i in range(n_bins):
        bin_lower = bins[i]
        bin_upper = bins[i + 1]

        if i == n_bins - 1:
            idx = np.where((p_arr >= bin_lower) & (p_arr <= bin_upper))[0]
        else:
            idx = np.where((p_arr >= bin_lower) & (p_arr < bin_upper))[0]

        count = len(idx)
        if count > 0:
            bin_acc = float(np.mean(y_arr[idx]))
            bin_conf = float(np.mean(p_arr[idx]))
            gap = abs(bin_acc - bin_conf)
            total_ece += (count / float(N)) * gap
            max_ce = max(max_ce, gap)
        else:
            bin_acc = 0.0
            bin_conf = float((bin_lower + bin_upper) / 2.0)
            gap = 0.0

        bin_table.append({
            "bin": f"{bin_lower:.1f}-{bin_upper:.1f}",
            "count": count,
            "mean_confidence": round(bin_conf, 4),
            "observed_accuracy": round(bin_acc, 4),
            "calibration_gap": round(gap, 4)
        })

    return round(total_ece, 4), round(max_ce, 4), bin_table


def extract_confidence_features(
    resolution_run_data: Dict[str, Any],
    verification_summary: Optional[ResolutionVerificationSummary] = None,
    retrieval_metadata: Optional[Dict[str, Any]] = None,
    duplicate_info: Optional[Dict[str, Any]] = None,
    severity_info: Optional[Dict[str, Any]] = None
) -> ConfidenceFeatureVector:
    """
    Extracts a structured 19-dimensional feature vector across retrieval,
    evidence quality, claim verification, resolution properties, duplicate signal, and severity.
    """
    ret_meta = retrieval_metadata or {}
    dup_info = duplicate_info or {}
    sev_info = severity_info or {}

    # A. Retrieval Strength
    top_dense = float(ret_meta.get("top_dense_similarity", 0.0))
    top_bm25 = float(ret_meta.get("top_bm25_score", 0.0))
    top_rrf = float(ret_meta.get("top_rrf_score", 0.0))
    score_gap = float(ret_meta.get("retrieval_score_gap", 0.0))

    # B. Evidence Quality
    completeness = float(ret_meta.get("evidence_completeness", 0.0))
    num_cases = int(ret_meta.get("num_retrieved_cases", 0))
    num_sources = int(ret_meta.get("num_usable_sources", 0))

    # C. Claim Verification Signals
    if verification_summary:
        tot_c = max(1, verification_summary.total_claims)
        sup_ratio = verification_summary.supported_count / float(tot_c)
        part_ratio = verification_summary.partially_supported_count / float(tot_c)
        unsup_ratio = verification_summary.unsupported_count / float(tot_c)
        contra_ratio = verification_summary.contradicted_count / float(tot_c)
        cit_cov = verification_summary.citation_coverage

        crit_unsup = sum(1 for c in verification_summary.claim_results if (c.is_critical or c.is_destructive) and c.verdict in ["UNSUPPORTED", "UNCLEAR"])
        crit_contra = sum(1 for c in verification_summary.claim_results if (c.is_critical or c.is_destructive) and c.verdict == "CONTRADICTED")
        num_claims = verification_summary.total_claims
    else:
        sup_ratio, part_ratio, unsup_ratio, contra_ratio, cit_cov = 0.0, 0.0, 1.0, 0.0, 0.0
        crit_unsup, crit_contra, num_claims = 1, 0, 1

    num_steps = len(resolution_run_data.get("steps", []))

    # E. Duplicate Signal
    dup_prob = float(dup_info.get("duplicate_probability", 0.0))
    strong_match = 1 if dup_prob >= 0.85 else 0

    # F. Severity Signal
    sev_conf = float(sev_info.get("severity_confidence", 0.0))

    return ConfidenceFeatureVector(
        top_dense_similarity=top_dense,
        top_bm25_score=top_bm25,
        top_rrf_score=top_rrf,
        retrieval_score_gap=score_gap,
        evidence_completeness=completeness,
        num_retrieved_cases=num_cases,
        num_usable_sources=num_sources,
        supported_claim_ratio=sup_ratio,
        partial_claim_ratio=part_ratio,
        unsupported_claim_ratio=unsup_ratio,
        contradiction_ratio=contra_ratio,
        citation_coverage=cit_cov,
        critical_unsupported_count=crit_unsup,
        critical_contradiction_count=crit_contra,
        num_factual_claims=num_claims,
        num_steps=num_steps,
        duplicate_probability=dup_prob,
        strong_historical_match_exists=strong_match,
        severity_confidence=sev_conf
    )


class ConfidenceCalibrationService:
    """
    Empirically Calibrated Confidence & Auto-Resolution Decision Layer.
    Predicts P(resolution_correct | features) using Logistic Regression calibration
    and enforces hard safety overrides & false-positive budgets.
    """

    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = Path(model_dir or settings.confidence_model_dir)
        self.model_path = self.model_dir / f"{settings.confidence_model_version}.joblib"
        self._model = None
        self._load_model()

    def _load_model(self):
        if self.model_path.exists():
            try:
                self._model = joblib.load(self.model_path)
                logger.info(f"Loaded confidence calibration model from {self.model_path}")
            except Exception as exc:
                logger.warning(f"Failed to load calibration model: {exc}")
                self._model = None
        else:
            logger.info(f"No existing calibration model at {self.model_path}. Will use fallback confidence scoring.")

    def fallback_confidence_score(self, features: ConfidenceFeatureVector) -> float:
        """
        Deterministic fallback formula for confidence estimation if ML model is unavailable.
        """
        score = (
            0.40 * features.supported_claim_ratio +
            0.20 * features.evidence_completeness +
            0.20 * features.citation_coverage +
            0.10 * min(1.0, features.top_dense_similarity) +
            0.10 * (1.0 - features.contradiction_ratio)
        )
        if features.critical_unsupported_count > 0 or features.critical_contradiction_count > 0:
            score *= 0.3
        return round(max(0.0, min(1.0, score)), 4)

    def predict_confidence(self, features: ConfidenceFeatureVector) -> float:
        """Predicts calibrated probability P(correct | features)."""
        if self._model is not None:
            try:
                X = np.array([features.to_list()], dtype=float)
                proba = float(self._model.predict_proba(X)[0, 1])
                return round(max(0.0, min(1.0, proba)), 4)
            except Exception as exc:
                logger.error(f"Error predicting probability with model: {exc}")

        return self.fallback_confidence_score(features)

    def select_threshold_under_budget(
        self,
        probabilities: List[float],
        y_true: List[int],
        max_false_auto_rate: float = 0.02
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Grid searches thresholds tau in [0.50, 0.95] to find the smallest threshold
        satisfying false_auto_resolution_rate <= max_false_auto_rate while maximizing coverage.
        """
        p_arr = np.array(probabilities, dtype=float)
        y_arr = np.array(y_true, dtype=int)
        N = max(1, len(y_arr))

        threshold_grid = np.linspace(0.50, 0.95, 46)
        analysis_table = []
        selected_threshold = settings.confidence_default_threshold

        best_coverage = -1.0

        for tau in threshold_grid:
            tau_val = round(float(tau), 4)
            auto_idx = np.where(p_arr >= tau_val)[0]
            auto_cnt = len(auto_idx)
            coverage = auto_cnt / float(N)

            if auto_cnt > 0:
                incorrect_auto = np.sum(y_arr[auto_idx] == 0)
                false_auto_rate = incorrect_auto / float(auto_cnt)
                precision = (auto_cnt - incorrect_auto) / float(auto_cnt)
            else:
                false_auto_rate = 0.0
                precision = 1.0

            analysis_table.append({
                "threshold": tau_val,
                "auto_resolve_count": auto_cnt,
                "coverage": round(coverage, 4),
                "precision": round(precision, 4),
                "false_auto_resolution_rate": round(false_auto_rate, 4),
                "human_review_rate": round(1.0 - coverage, 4)
            })

            if false_auto_rate <= max_false_auto_rate and auto_cnt > 0:
                if coverage > best_coverage:
                    best_coverage = coverage
                    selected_threshold = tau_val

        return selected_threshold, analysis_table

    def compute_confidence_and_decision(
        self,
        features: ConfidenceFeatureVector,
        verification_summary: Optional[ResolutionVerificationSummary] = None,
        custom_threshold: Optional[float] = None,
        ticket_id: Optional[int] = None,
        resolution_run_id: Optional[str] = None,
        session: Optional[Session] = None
    ) -> ConfidencePrediction:
        """
        Calculates calibrated confidence, evaluates hard safety overrides & reason codes,
        makes final AUTO_RESOLVE / HUMAN_REVIEW decision, and optionally persists record.
        """
        calibrated_conf = self.predict_confidence(features)
        threshold = custom_threshold if custom_threshold is not None else settings.confidence_default_threshold

        reason_codes: List[str] = []

        # Feature Reason Codes
        if features.top_dense_similarity >= 0.75:
            reason_codes.append("HIGH_RETRIEVAL_SUPPORT")
        else:
            reason_codes.append("LOW_RETRIEVAL_SUPPORT")

        if features.evidence_completeness >= 0.70:
            reason_codes.append("HIGH_EVIDENCE_COMPLETENESS")
        else:
            reason_codes.append("LOW_EVIDENCE_COMPLETENESS")

        if self._model is None:
            reason_codes.append("CALIBRATION_MODEL_UNAVAILABLE")

        # Hard Safety Overrides Hierarchy
        decision = "HUMAN_REVIEW"

        if verification_summary is None:
            decision = "VERIFICATION_FAILED"
            reason_codes.append("VERIFIER_UNAVAILABLE")
        elif verification_summary.has_critical_failure or features.critical_unsupported_count > 0:
            decision = "HUMAN_REVIEW"
            reason_codes.append("CRITICAL_CLAIM_FAILURE")
        elif verification_summary.contradicted_count > 0 or features.contradiction_ratio > 0.0:
            decision = "HUMAN_REVIEW"
            reason_codes.append("CONTRADICTION_PRESENT")
        elif verification_summary.unsupported_count > 0:
            reason_codes.append("UNSUPPORTED_CLAIMS_PRESENT")
            if calibrated_conf < threshold:
                decision = "HUMAN_REVIEW"
                reason_codes.append("CONFIDENCE_BELOW_THRESHOLD")
            else:
                decision = "AUTO_RESOLVE"
                reason_codes.append("CALIBRATED_CONFIDENCE_ABOVE_THRESHOLD")
        elif calibrated_conf < threshold:
            decision = "HUMAN_REVIEW"
            reason_codes.append("CONFIDENCE_BELOW_THRESHOLD")
        else:
            decision = "AUTO_RESOLVE"
            reason_codes.append("ALL_CLAIMS_SUPPORTED")
            reason_codes.append("CALIBRATED_CONFIDENCE_ABOVE_THRESHOLD")

        now_utc = datetime.now(timezone.utc)
        conf_run_id = f"conf_{now_utc.strftime('%Y%m%d_%H%M%S_%f')[:20]}"

        pred = ConfidencePrediction(
            confidence_run_id=conf_run_id,
            ticket_id=ticket_id,
            resolution_run_id=resolution_run_id,
            calibrated_confidence=calibrated_conf,
            decision=decision,
            threshold=threshold,
            reason_codes=list(set(reason_codes)),
            model_version=settings.confidence_model_version,
            feature_version=settings.confidence_feature_version,
            threshold_version=settings.confidence_threshold_version,
            features=features
        )

        # DB Persistence
        if session is not None:
            rec = ConfidenceRun(
                confidence_run_id=conf_run_id,
                ticket_id=ticket_id,
                resolution_run_id=None,
                verification_run_id=None,
                calibrated_confidence=calibrated_conf,
                decision=decision,
                selected_threshold=threshold,
                model_version=settings.confidence_model_version,
                feature_version=settings.confidence_feature_version,
                threshold_version=settings.confidence_threshold_version,
                features_json=features.model_dump(),
                reason_codes=pred.reason_codes,
                created_at=now_utc
            )
            session.add(rec)
            session.commit()

        return pred


def render_human_readable_confidence(pred: ConfidencePrediction) -> str:
    """Renders formatted human-readable confidence report."""
    lines = []
    lines.append("===================================================================================")
    lines.append("                CALIBRATED CONFIDENCE & AUTO-RESOLUTION REPORT                     ")
    lines.append("===================================================================================")
    lines.append(f"CONFIDENCE RUN ID:   {pred.confidence_run_id}")
    lines.append(f"TICKET ID:           {pred.ticket_id or 'N/A'}")
    lines.append(f"CALIBRATED CONFIDENCE:{pred.calibrated_confidence * 100:.2f}%")
    lines.append(f"TARGET THRESHOLD:    {pred.threshold * 100:.1f}%")
    lines.append(f"FINAL DECISION:      {pred.decision}")
    lines.append("-----------------------------------------------------------------------------------")
    lines.append(f"MODEL VERSION:       {pred.model_version}")
    lines.append(f"FEATURE VERSION:     {pred.feature_version}")
    lines.append("REASON CODES:")
    for code in pred.reason_codes:
        desc = REASON_CODES.get(code, "")
        lines.append(f"  - [{code}] {desc}")
    lines.append("-----------------------------------------------------------------------------------")
    lines.append("EXTRACTED FEATURE VECTOR:")
    feat_dict = pred.features.model_dump()
    for k, v in feat_dict.items():
        val_str = f"{v:.4f}" if isinstance(v, float) else str(v)
        lines.append(f"  - {k:<30}: {val_str}")
    lines.append("===================================================================================\n")
    return "\n".join(lines)
