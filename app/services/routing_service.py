import os
import re
import joblib
import logging
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Set

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from config import settings
from app.database.models import (
    Issue,
    Label,
    Repository,
    RoutingTarget,
    RoutingPrediction,
    RootCauseAssignment,
)
from app.schemas.routing_schemas import (
    RoutingTargetInfo,
    TopKRoutingCandidate,
    RoutingResult,
)

logger = logging.getLogger("routing_engine")

GENERIC_NON_COMPONENT_LABELS = {
    "bug", "feature", "enhancement", "documentation", "question", "duplicate",
    "wontfix", "invalid", "help wanted", "good first issue", "triage", "priority",
    "severity", "status", "needs-info", "verified", "confirmed"
}


def extract_component_from_labels(label_names: List[str]) -> Optional[str]:
    """
    Extracts a canonical component/area name from an issue's labels.
    Ignores generic bug/severity/status tags.
    """
    for lbl in label_names:
        lbl_clean = lbl.strip().lower()
        if lbl_clean.startswith("area/"):
            return lbl_clean.split("area/")[1]
        elif lbl_clean.startswith("component:"):
            return lbl_clean.split("component:")[1]

    # Fallback to direct component match
    for lbl in label_names:
        lbl_clean = lbl.strip().lower()
        if lbl_clean not in GENERIC_NON_COMPONENT_LABELS and not any(kw in lbl_clean for kw in ["p0", "p1", "p2", "p3", "sev"]):
            return lbl_clean

    return None


def map_component_to_team(component: str) -> str:
    """Derives a normalized team ownership target from a component string."""
    comp_clean = component.strip().lower()
    if comp_clean == "general" or not comp_clean:
        return settings.routing_default_queue

    mapping = {
        "terminal": "terminal-maintainers",
        "editor": "core-editor-team",
        "extensions": "extensions-team",
        "git": "vcs-integrations-team",
        "notebook": "data-science-notebooks",
        "api": "platform-api-team",
        "testing": "qa-automation-team",
        "languages": "language-tools-team",
        "debugger": "debugging-runtime-team"
    }
    return mapping.get(comp_clean, f"{comp_clean}-team")


class RoutingEngineService:
    """
    Component & Ownership Routing Engine.
    Combines ML classification, baseline retrieval majority, duplicate signals,
    and root-cause purity scoring to assign support tickets to component teams.
    """

    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = Path(model_dir or settings.routing_model_dir)
        self.model_path = self.model_dir / f"{settings.routing_model_version}.joblib"
        self._model = None
        self._classes: List[str] = []
        self._load_model()

    def _load_model(self):
        if self.model_path.exists():
            try:
                data = joblib.load(self.model_path)
                self._model = data.get("model")
                self._classes = data.get("classes", [])
                logger.info(f"Loaded ML routing model with classes {self._classes} from {self.model_path}")
            except Exception as exc:
                logger.warning(f"Failed to load ML routing model: {exc}")
                self._model = None
        else:
            logger.info(f"No existing ML routing model at {self.model_path}. Will use baseline retrieval router.")

    def baseline_retrieval_routing(
        self,
        retrieved_cases: List[Dict[str, Any]]
    ) -> List[TopKRoutingCandidate]:
        """
        Baseline Router: Computes component frequency across top retrieved historical cases.
        """
        counts: Dict[str, int] = {}
        for case in retrieved_cases:
            labels = case.get("labels", [])
            comp = extract_component_from_labels(labels) or "general"
            counts[comp] = counts.get(comp, 0) + 1

        total = max(1, len(retrieved_cases))
        candidates = []
        for comp, cnt in counts.items():
            prob = round(cnt / float(total), 4)
            team = map_component_to_team(comp)
            candidates.append(TopKRoutingCandidate(
                component=comp,
                team=team,
                probability=prob,
                signal_source="baseline_retrieval"
            ))

        candidates.sort(key=lambda x: x.probability, reverse=True)
        return candidates if candidates else [TopKRoutingCandidate(
            component="general",
            team=settings.routing_default_queue,
            probability=0.5,
            signal_source="baseline_retrieval"
        )]

    def predict_route(
        self,
        issue_embedding: Optional[List[float]] = None,
        retrieved_cases: Optional[List[Dict[str, Any]]] = None,
        duplicate_info: Optional[Dict[str, Any]] = None,
        root_cause_info: Optional[Dict[str, Any]] = None,
        ticket_id: Optional[int] = None,
        session: Optional[Session] = None
    ) -> RoutingResult:
        """
        Fuses multi-source routing signals (ML classifier, retrieval baseline, duplicate match, root-cause purity)
        to return a validated RoutingResult.
        """
        candidates: List[TopKRoutingCandidate] = []

        # Signal 1: ML Model Probability (if embedding and trained model exist)
        if self._model is not None and issue_embedding is not None:
            try:
                X = np.array([issue_embedding], dtype=float)
                probas = self._model.predict_proba(X)[0]
                for cls_name, p in zip(self._classes, probas):
                    candidates.append(TopKRoutingCandidate(
                        component=cls_name,
                        team=map_component_to_team(cls_name),
                        probability=round(float(p), 4),
                        signal_source="ml_model"
                    ))
            except Exception as exc:
                logger.error(f"ML routing prediction error: {exc}")

        # Signal 2: Baseline Retrieval Signals
        if retrieved_cases:
            base_cands = self.baseline_retrieval_routing(retrieved_cases)
            if not candidates:
                candidates.extend(base_cands)
            else:
                # Score Fusion: Boost ML candidates using retrieval weights
                comp_weights = {c.component: c.probability for c in base_cands}
                fused = []
                for cand in candidates:
                    ret_p = comp_weights.get(cand.component, 0.0)
                    fused_p = round(0.6 * cand.probability + 0.4 * ret_p, 4)
                    fused.append(TopKRoutingCandidate(
                        component=cand.component,
                        team=cand.team,
                        probability=fused_p,
                        signal_source="score_fusion"
                    ))
                candidates = fused

        # Signal 3: Confirmed Duplicate Historical Component Prior
        if duplicate_info and duplicate_info.get("duplicate_probability", 0.0) >= 0.85:
            dup_case = duplicate_info.get("top_match_issue", {})
            dup_labels = dup_case.get("labels", [])
            dup_comp = extract_component_from_labels(dup_labels)
            if dup_comp:
                candidates.insert(0, TopKRoutingCandidate(
                    component=dup_comp,
                    team=map_component_to_team(dup_comp),
                    probability=0.90,
                    signal_source="duplicate_match"
                ))

        # Fallback if no signals produced candidates
        if not candidates:
            candidates = [TopKRoutingCandidate(
                component="general",
                team=settings.routing_default_queue,
                probability=0.50,
                signal_source="fallback"
            )]

        # Sort descending by probability
        candidates.sort(key=lambda x: x.probability, reverse=True)

        top_cand = candidates[0]
        top_comp = top_cand.component
        top_prob = top_cand.probability

        # Check for Low-Support / Unknown Component
        is_low_support = False
        is_unknown = False

        if session is not None and top_comp != "general":
            # Check historical issue count in database
            target_rec = session.scalar(
                select(RoutingTarget).where(RoutingTarget.component == top_comp)
            )
            if target_rec:
                if target_rec.historical_issue_count < settings.routing_min_samples_per_component:
                    is_low_support = True
            else:
                is_unknown = True

        # Check threshold
        if top_prob < settings.routing_min_confidence or is_unknown or is_low_support:
            final_team = settings.routing_default_queue
        else:
            final_team = top_cand.team

        now_utc = datetime.now(timezone.utc)
        pred_id = f"route_{now_utc.strftime('%Y%m%d_%H%M%S_%f')[:20]}"

        res = RoutingResult(
            routing_prediction_id=pred_id,
            ticket_id=ticket_id,
            predicted_component=top_comp,
            predicted_team=final_team,
            routing_probability=top_prob,
            top_k=candidates[:3],
            is_low_support=is_low_support,
            is_unknown_target=is_unknown,
            model_version=settings.routing_model_version
        )

        # DB Persistence
        if session is not None:
            db_rec = RoutingPrediction(
                routing_prediction_id=pred_id,
                ticket_id=ticket_id,
                predicted_target=f"component:{top_comp}",
                predicted_component=top_comp,
                routing_probability=top_prob,
                top_k_targets=[c.model_dump() for c in candidates[:3]],
                model_version=settings.routing_model_version,
                created_at=now_utc
            )
            session.add(db_rec)
            session.commit()

        return res
