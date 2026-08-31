import os
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import select

from config import settings
from app.database.models import Issue, Repository, Comment, PullRequest, ResolutionRun, ResolutionClaimRecord
from app.schemas.resolution_schemas import (
    ResolutionRequest,
    EvidenceCase,
    EvidencePackage,
    ResolutionStep,
    ResolutionClaim,
    ResolutionResponse,
)
from app.services.hybrid_retrieval_service import HybridRetrievalService, calculate_resolution_evidence
from app.services.llm_client import LLMClient

logger = logging.getLogger("grounded_resolution")

SYSTEM_PROMPT_V1 = """You are an expert Autonomous Support Triage & Resolution AI Engineer for SupportPilot.
Your task is to analyze an incoming support ticket and generate a structured, evidence-grounded technical resolution based ONLY on the provided historical resolved cases.

CRITICAL CONSTRAINTS:
1. Use ONLY the supplied historical evidence cases. Do NOT invent facts, commands, fixes, or API endpoints.
2. Every atomic claim in "claims" and every step in "steps" MUST cite one or more source IDs (e.g. "issue:123" or "pr:456") strictly from the provided evidence cases.
3. If the provided evidence is insufficient or lacks a clear fix, set "resolution_type" to "insufficient_evidence", state that evidence is insufficient, and set "needs_human_review" to true.
4. Distinguish clearly between:
   - "confirmed_historical_resolution": Strong direct evidence with resolved PR or closing fix comment.
   - "evidence_based_recommendation": Strong indirect evidence or pattern similarity.
   - "insufficient_evidence": Weak or no relevant resolution evidence.
5. Do NOT remove or modify technical error codes, stack traces, version numbers, package names, or API identifiers.
6. Return output in strict JSON adhering to the required schema.
"""


def calculate_case_completeness(
    has_body: bool,
    has_comments: bool,
    has_closing_comment: bool,
    has_prs: bool,
    has_resolution_text: bool
) -> float:
    """
    Calculates evidence completeness indicator (0.0 to 1.0).
    This is NOT model confidence; it measures available source evidence.
    """
    score = 0.0
    if has_body:
        score += 0.2
    if has_comments:
        score += 0.2
    if has_closing_comment:
        score += 0.2
    if has_prs:
        score += 0.2
    if has_resolution_text:
        score += 0.2
    return round(min(1.0, score), 2)


def prioritize_case_context(
    title: str,
    body: str,
    comments: List[str],
    pr_info: List[Dict[str, Any]],
    max_chars: int = 1500
) -> Tuple[str, str, bool]:
    """
    Prioritizes context ordering:
    1. Closing/resolution comment
    2. Linked PR title/description
    3. Issue body
    4. Other comments
    Preserves technical tokens.
    Returns (problem_snippet, resolution_snippet, truncated_flag).
    """
    truncated = False

    # Identify closing or fix comments
    closing_comments = []
    other_comments = []

    for c in comments:
        c_lower = c.lower()
        if any(kw in c_lower for kw in ["fixed", "resolved", "pr #", "merged", "close"]):
            closing_comments.append(c)
        else:
            other_comments.append(c)

    res_parts = []

    # 1. Closing comments
    if closing_comments:
        res_parts.append("CLOSING COMMENT:\n" + "\n".join(closing_comments[:2]))

    # 2. Linked PRs
    if pr_info:
        pr_text = "\n".join([f"PR #{pr.get('number')}: {pr.get('title', '')}" for pr in pr_info[:2]])
        res_parts.append("LINKED PRS:\n" + pr_text)

    # 3. Other comments
    if other_comments and len("\n".join(res_parts)) < max_chars // 2:
        res_parts.append("COMMENTS:\n" + "\n".join(other_comments[:2]))

    resolution_snippet = "\n\n".join(res_parts)
    problem_snippet = f"TITLE: {title}\nBODY: {body[:800]}"

    if len(problem_snippet) > max_chars // 2:
        problem_snippet = problem_snippet[: max_chars // 2] + "\n...[truncated]"
        truncated = True

    if len(resolution_snippet) > max_chars // 2:
        resolution_snippet = resolution_snippet[: max_chars // 2] + "\n...[truncated]"
        truncated = True

    return problem_snippet, resolution_snippet, truncated


class GroundedResolutionService:
    """
    Service orchestrating Hybrid Retrieval, Evidence Package construction,
    LLM structured generation, Source-ID validation, and persistence.
    """

    def __init__(
        self,
        retrieval_service: Optional[HybridRetrievalService] = None,
        llm_client: Optional[LLMClient] = None,
        db_session: Optional[Session] = None
    ):
        self.retrieval_service = retrieval_service or HybridRetrievalService(db_session=db_session)
        self.llm_client = llm_client or LLMClient()

    def build_evidence_package(
        self,
        request: ResolutionRequest,
        session: Session,
        max_cases: int = 8,
        max_chars_per_case: int = 1500,
        max_total_chars: int = 12000
    ) -> EvidencePackage:
        """
        Calls Hybrid Retrieval and constructs a deterministic Evidence Package.
        """
        query_text = f"{request.title}\n{request.body}".strip()

        # Perform hybrid retrieval
        retrieved_results = self.retrieval_service.retrieve_resolved_cases(
            query_text=query_text,
            repository_id=request.repository_id,
            query_issue_id=request.issue_number,
            top_k=max_cases,
            db_session=session
        )

        evidence_cases: List[EvidenceCase] = []
        total_chars = 0
        overall_truncated = False

        for res in retrieved_results:
            issue_id = res["issue_id"]
            iss = session.get(Issue, issue_id)
            if not iss:
                continue

            repo_full_name = iss.repository.full_name if iss.repository else res.get("repository", "unknown")
            comments_text = [c.body for c in iss.comments if c.body]
            prs_data = [{"number": pr.pr_number, "title": f"PR #{pr.pr_number}", "url": pr.html_url or ""} for pr in iss.pull_requests]

            # Calculate evidence completeness
            ev_score, ev_flags = calculate_resolution_evidence(
                has_comments=bool(comments_text),
                has_prs=bool(prs_data),
                comments_text=" ".join(comments_text),
                pr_text=" ".join([f"PR #{p['number']}" for p in prs_data])
            )
            completeness = calculate_case_completeness(
                has_body=bool(iss.body),
                has_comments=bool(comments_text),
                has_closing_comment=ev_flags.get("has_closing_comment", False),
                has_prs=bool(prs_data),
                has_resolution_text=ev_flags.get("has_resolution_text", False)
            )

            # Prioritize and truncate context
            prob_snip, res_snip, case_truncated = prioritize_case_context(
                title=iss.title,
                body=iss.body or "",
                comments=comments_text,
                pr_info=prs_data,
                max_chars=max_chars_per_case
            )

            if case_truncated:
                overall_truncated = True

            source_urls = []
            if iss.html_url:
                source_urls.append(iss.html_url)
            for p in prs_data:
                if p.get("url"):
                    source_urls.append(p["url"])

            case_id = f"issue:{iss.issue_number}"

            evidence_case = EvidenceCase(
                case_id=case_id,
                issue_number=iss.issue_number,
                repository=repo_full_name,
                title=iss.title,
                problem_snippet=prob_snip,
                resolution_snippet=res_snip,
                pull_requests=prs_data,
                source_urls=source_urls,
                retrieval_score=round(res["final_score"], 6),
                evidence_completeness=completeness
            )

            case_chars = len(prob_snip) + len(res_snip)
            if total_chars + case_chars > max_total_chars:
                overall_truncated = True
                break

            total_chars += case_chars
            evidence_cases.append(evidence_case)

        query_ticket = {
            "title": request.title,
            "body": request.body,
            "repository_id": request.repository_id,
            "severity_prediction": request.severity_prediction,
            "root_cause_cluster": request.root_cause_cluster,
        }

        return EvidencePackage(
            query_ticket=query_ticket,
            cases=evidence_cases,
            total_cases=len(evidence_cases),
            truncated=overall_truncated
        )

    def validate_source_ids(
        self,
        response_data: Dict[str, Any],
        valid_source_ids: Set[str]
    ) -> Tuple[Dict[str, Any], float, float]:
        """
        Validates whether all cited source_ids exist in the evidence package.
        Calculates citation_coverage and unsupported_claim_rate.
        """
        claims = response_data.get("claims", [])
        steps = response_data.get("steps", [])

        if not claims:
            return response_data, 0.0, 0.0

        valid_claim_count = 0
        unsupported_claim_count = 0

        for claim in claims:
            cited_sources = claim.get("source_ids", [])
            if not cited_sources:
                claim["source_validation_status"] = "missing_sources"
                unsupported_claim_count += 1
                continue

            invalid_refs = [sid for sid in cited_sources if sid not in valid_source_ids]
            if invalid_refs:
                claim["source_validation_status"] = f"invalid_references_{invalid_refs}"
                unsupported_claim_count += 1
            else:
                claim["source_validation_status"] = "valid"
                valid_claim_count += 1

        # Validate step source IDs as well
        for step in steps:
            cited_sources = step.get("source_ids", [])
            invalid_refs = [sid for sid in cited_sources if sid not in valid_source_ids]
            if invalid_refs:
                step["source_ids"] = [sid for sid in cited_sources if sid in valid_source_ids]

        total_claims = len(claims)
        citation_coverage = round(valid_claim_count / float(total_claims), 4) if total_claims > 0 else 0.0
        unsupported_claim_rate = round(unsupported_claim_count / float(total_claims), 4) if total_claims > 0 else 0.0

        response_data["citation_coverage"] = citation_coverage
        response_data["unsupported_claim_rate"] = unsupported_claim_rate

        return response_data, citation_coverage, unsupported_claim_rate

    def generate_resolution(
        self,
        request: ResolutionRequest,
        session: Session
    ) -> Tuple[ResolutionResponse, EvidencePackage, str]:
        """
        Executes complete Grounded Resolution pipeline:
        1. Retrieval & Evidence Package build
        2. LLM structured resolution generation
        3. Source-ID validation
        4. DB Persistence & Artifact saving
        """
        start_time = time.time()
        now_utc = datetime.now(timezone.utc)
        run_id = f"res_{now_utc.strftime('%Y%m%d_%H%M%S_%f')[:20]}"

        # 1. Build Evidence Package
        evidence_pkg = self.build_evidence_package(
            request=request,
            session=session,
            max_cases=settings.resolution_max_cases,
            max_chars_per_case=settings.resolution_max_chars_per_case,
            max_total_chars=settings.resolution_max_total_context_chars
        )

        valid_source_ids = set()
        for case in evidence_pkg.cases:
            valid_source_ids.add(case.case_id)
            for pr in case.pull_requests:
                if pr.get("number"):
                    valid_source_ids.add(f"pr:{pr['number']}")

        # 2. Format LLM prompt
        if not evidence_pkg.cases:
            logger.warning("No historical evidence cases retrieved. Returning safe fallback.")
            raw_response = self.llm_client._build_fallback_response()
        else:
            evidence_json_str = json.dumps(evidence_pkg.model_dump(), indent=2)
            user_prompt = (
                f"INCOMING TICKET:\nTitle: {request.title}\nBody: {request.body}\n"
                f"Severity Prediction: {request.severity_prediction or 'N/A'}\n"
                f"Root Cause Cluster: {request.root_cause_cluster or 'N/A'}\n\n"
                f"HISTORICAL EVIDENCE CASES:\n{evidence_json_str}\n\n"
                "Generate a grounded technical resolution adhering strictly to the required schema."
            )

            raw_response = self.llm_client.generate_structured(
                prompt=user_prompt,
                system_prompt=SYSTEM_PROMPT_V1,
                response_schema=ResolutionResponse
            )

        # 3. Source-ID Validation
        validated_dict, coverage, unsupported_rate = self.validate_source_ids(
            raw_response, valid_source_ids
        )

        # Force human review if evidence is insufficient or unsupported claims exist
        needs_review = (
            validated_dict.get("resolution_type") == "insufficient_evidence"
            or unsupported_rate > 0.0
            or coverage < 1.0
            or not evidence_pkg.cases
        )
        validated_dict["needs_human_review"] = needs_review

        resolution_res = ResolutionResponse.model_validate(validated_dict)

        latency = round(time.time() - start_time, 4)

        # 4. DB Persistence
        run_record = ResolutionRun(
            run_id=run_id,
            issue_id=request.issue_number,
            repository_id=request.repository_id,
            retrieval_run_id=f"retrieval_{run_id}",
            model_name=settings.resolution_llm_model,
            prompt_version=settings.resolution_prompt_version,
            resolution_type=resolution_res.resolution_type,
            needs_human_review=resolution_res.needs_human_review,
            citation_coverage=resolution_res.citation_coverage,
            unsupported_claim_rate=resolution_res.unsupported_claim_rate,
            latency_seconds=latency,
            validation_status="passed" if unsupported_rate == 0.0 else "warnings",
            raw_output=resolution_res.model_dump(),
            created_at=now_utc
        )
        session.add(run_record)
        session.flush()

        for cl in resolution_res.claims:
            claim_rec = ResolutionClaimRecord(
                claim_id=cl.claim_id,
                resolution_run_id=run_record.id,
                claim_text=cl.text,
                source_ids=cl.source_ids,
                source_validation_status=cl.source_validation_status or "valid",
                verification_status="pending",
                created_at=now_utc
            )
            session.add(claim_rec)

        session.commit()

        # 5. Save Artifacts
        artifact_dir = Path("artifacts/resolution") / f"run_{run_id}"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        with open(artifact_dir / "resolution.json", "w", encoding="utf-8") as f:
            json.dump(resolution_res.model_dump(), f, indent=2)

        with open(artifact_dir / "evidence.json", "w", encoding="utf-8") as f:
            json.dump(evidence_pkg.model_dump(), f, indent=2)

        metadata = {
            "run_id": run_id,
            "latency_seconds": latency,
            "model_name": settings.resolution_llm_model,
            "prompt_version": settings.resolution_prompt_version,
            "total_cases_retrieved": evidence_pkg.total_cases,
            "citation_coverage": coverage,
            "unsupported_claim_rate": unsupported_rate,
            "created_at": now_utc.isoformat()
        }
        with open(artifact_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        human_readable = render_human_readable_resolution(resolution_res, evidence_pkg)
        with open(artifact_dir / "human_readable.txt", "w", encoding="utf-8") as f:
            f.write(human_readable)

        logger.info(f"Grounded resolution generated successfully. Run ID: {run_id}, Latency: {latency}s")
        return resolution_res, evidence_pkg, run_id


def render_human_readable_resolution(
    response: ResolutionResponse,
    evidence: EvidencePackage
) -> str:
    """Renders formatted human-readable resolution report for CLI and UI output."""
    lines = []
    lines.append("===================================================================================")
    lines.append("                       GROUNDED RESOLUTION REPORT                                   ")
    lines.append("===================================================================================")
    lines.append(f"RESOLUTION TYPE:     {response.resolution_type.upper()}")
    lines.append(f"HUMAN REVIEW NEEDED: {response.needs_human_review}")
    lines.append(f"CITATION COVERAGE:   {response.citation_coverage * 100:.1f}%")
    lines.append(f"UNSUPPORTED CLAIMS:  {response.unsupported_claim_rate * 100:.1f}%")
    lines.append("-----------------------------------------------------------------------------------")
    lines.append("SUMMARY:")
    lines.append(f"  {response.summary}")
    lines.append("\nDIAGNOSIS:")
    lines.append(f"  {response.diagnosis}")
    lines.append("\nRECOMMENDED RESOLUTION:")
    lines.append(f"  {response.recommended_resolution}")
    lines.append("\nSTEPS:")
    for step in response.steps:
        sources_str = ", ".join(step.source_ids) if step.source_ids else "None"
        lines.append(f"  {step.step}. {step.instruction} [Sources: {sources_str}]")
    lines.append("\nCLAIMS & CITATIONS:")
    for claim in response.claims:
        sources_str = ", ".join(claim.source_ids) if claim.source_ids else "None"
        lines.append(f"  [{claim.claim_id}] {claim.text}")
        lines.append(f"       Sources: {sources_str} | Status: {claim.source_validation_status}")
    lines.append("\nLIMITATIONS & UNCERTAINTIES:")
    for lim in response.limitations:
        lines.append(f"  - {lim}")
    lines.append("\nRETRIEVED EVIDENCE SOURCES:")
    for case in evidence.cases:
        lines.append(f"  - [{case.case_id}] {case.title} (Score: {case.retrieval_score}, Completeness: {case.evidence_completeness})")
        for url in case.source_urls:
            lines.append(f"       URL: {url}")
    lines.append("===================================================================================\n")
    return "\n".join(lines)
