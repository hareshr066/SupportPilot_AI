import os
import re
import json
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import select

from config import settings
from app.database.models import (
    Issue,
    Repository,
    Comment,
    PullRequest,
    ResolutionRun,
    ResolutionClaimRecord,
    VerificationRun,
    ClaimVerificationRecord,
)
from app.schemas.verification_schemas import (
    EvidenceSpan,
    LLMVerifierOutput,
    ClaimVerificationResult,
    ResolutionVerificationSummary,
)
from app.services.llm_client import LLMClient

logger = logging.getLogger("claim_verification")

VERIFIER_SYSTEM_PROMPT_V1 = """You are an independent, objective Claim Verification Engine for SupportPilot.
Your task is to determine whether a given factual claim is supported by the provided source evidence text excerpts.

VERDICT LABELS:
- SUPPORTED: The evidence explicitly and directly supports the entire claim.
- PARTIALLY_SUPPORTED: The evidence supports part of the claim, but not all stated facts.
- UNSUPPORTED: The evidence does not provide sufficient facts to confirm or deny the claim.
- CONTRADICTED: The evidence directly contradicts or conflicts with the claim.
- UNCLEAR: The evidence is ambiguous, incomplete, or impossible to verify.

RULES:
1. Base your verdict strictly on the supplied source evidence excerpts. Do NOT use outside knowledge or assumptions.
2. If evidence contradicts any part of the claim, output CONTRADICTED.
3. If evidence is missing or insufficient, output UNCLEAR or UNSUPPORTED.
4. Extract the exact evidence text passage supporting your verdict into evidence_spans.
5. Set support_strength between 0.0 (no support/contradicted) and 1.0 (perfect explicit support).
6. Provide a concise verification explanation.

Return strict JSON adhering to the required output schema.
"""


def decompose_claim(claim_id: str, claim_text: str) -> List[Tuple[str, Optional[str], str]]:
    """
    Decomposes compound factual claims into atomic sub-claims.
    Returns list of tuples: (atomic_claim_id, parent_claim_id, atomic_claim_text).
    """
    # Look for conjunctions connecting distinct factual clauses
    clauses = re.split(r'\b(?:and also|and was|and is|and affects|and released in)\b', claim_text, flags=re.IGNORECASE)
    
    if len(clauses) <= 1 or len(claim_text) < 40:
        return [(claim_id, None, claim_text.strip())]

    sub_claims = []
    for idx, c in enumerate(clauses):
        c_str = c.strip()
        if c_str:
            sub_id = f"{claim_id}_{chr(97 + idx)}"
            sub_claims.append((sub_id, claim_id, c_str))

    return sub_claims if sub_claims else [(claim_id, None, claim_text.strip())]


def classify_claim_criticality(claim_text: str) -> Tuple[bool, bool]:
    """
    Determines if a claim is critical or involves destructive operations.
    Returns (is_critical, is_destructive).
    """
    text_lower = claim_text.lower()

    critical_keywords = [
        "diagnosis", "fixed in", "resolved by", "upgrade to", "version",
        "resolution", "root cause", "recommended", "patch", "v2.", "v1.", "v3.", "v0."
    ]
    is_critical = any(kw in text_lower for kw in critical_keywords)

    destructive_keywords = [
        "delete", "rm ", "drop ", "truncate", "migration", "permission",
        "chmod", "chown", "sudo", "credential", "reset", "purge", "destroy"
    ]
    is_destructive = any(kw in text_lower for kw in destructive_keywords)

    return is_critical, is_destructive


def extract_relevant_evidence_snippets(
    claim_text: str,
    source_id: str,
    source_content: str,
    top_k: int = 3,
    max_chars: int = 1200
) -> List[EvidenceSpan]:
    """
    Splits source content into passages and extracts top K passages relevant to claim_text.
    """
    if not source_content.strip():
        return []

    # Split source content into sentences / lines
    raw_passages = re.split(r'(?<=[.!?])\s+|\n+', source_content)
    passages = [p.strip() for p in raw_passages if len(p.strip()) > 10]

    if not passages:
        return [EvidenceSpan(source_id=source_id, text=source_content[:max_chars], relevance_score=0.5)]

    claim_tokens = set(re.findall(r'\w+', claim_text.lower()))

    scored_passages = []
    for p in passages:
        p_tokens = set(re.findall(r'\w+', p.lower()))
        if not p_tokens:
            continue
        overlap = len(claim_tokens.intersection(p_tokens))
        score = overlap / float(len(claim_tokens)) if claim_tokens else 0.0
        scored_passages.append((score, p))

    # Sort descending by relevance score
    scored_passages.sort(key=lambda x: x[0], reverse=True)

    spans = []
    total_len = 0

    for score, text in scored_passages[:top_k]:
        if total_len + len(text) > max_chars:
            text = text[: max_chars - total_len]
        spans.append(EvidenceSpan(
            source_id=source_id,
            text=text,
            relevance_score=round(score, 4)
        ))
        total_len += len(text)
        if total_len >= max_chars:
            break

    return spans


class ClaimVerificationService:
    """
    Independent Claim Verification Service that validates resolution claims
    against batch-fetched database evidence, supporting two-level verification,
    caching, persistence, and evaluation.
    """

    def __init__(
        self,
        verifier_llm_client: Optional[LLMClient] = None,
        db_session: Optional[Session] = None
    ):
        self.verifier_llm_client = verifier_llm_client or LLMClient(
            model_name=settings.verifier_llm_model,
            temperature=settings.verifier_temperature,
            max_retries=settings.verifier_max_retries
        )
        self.db_session = db_session
        self._verification_cache: Dict[str, Dict[str, Any]] = {}

    def _get_cache_key(self, claim_text: str, source_contents: str) -> str:
        raw = f"{claim_text}||{source_contents}||{settings.verifier_prompt_version}||{settings.verifier_llm_model}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def batch_fetch_sources(
        self,
        source_ids: List[str],
        session: Session
    ) -> Dict[str, Dict[str, Any]]:
        """
        Batch-fetches source content for issues, comments, and PRs from PostgreSQL.
        Prevents N+1 database queries.
        """
        resolved_sources: Dict[str, Dict[str, Any]] = {}

        issue_numbers: Set[int] = set()
        pr_numbers: Set[int] = set()

        for sid in source_ids:
            if sid.startswith("issue:"):
                try:
                    issue_numbers.add(int(sid.split(":")[1]))
                except ValueError:
                    pass
            elif sid.startswith("pr:"):
                try:
                    pr_numbers.add(int(sid.split(":")[1]))
                except ValueError:
                    pass

        # Batch query Issues
        if issue_numbers:
            issues = session.scalars(
                select(Issue).where(Issue.issue_number.in_(issue_numbers))
            ).all()
            for iss in issues:
                sid = f"issue:{iss.issue_number}"
                comment_text = "\n".join([c.body for c in iss.comments if c.body])
                full_text = f"TITLE: {iss.title}\nBODY: {iss.body or ''}\nCOMMENTS:\n{comment_text}".strip()
                resolved_sources[sid] = {
                    "source_id": sid,
                    "source_type": "github_issue",
                    "repository": iss.repository.full_name if iss.repository else "unknown",
                    "number": iss.issue_number,
                    "url": iss.html_url or "",
                    "content": full_text
                }

        # Batch query Pull Requests
        if pr_numbers:
            prs = session.scalars(
                select(PullRequest).where(PullRequest.pr_number.in_(pr_numbers))
            ).all()
            for pr in prs:
                sid = f"pr:{pr.pr_number}"
                content_text = f"PR #{pr.pr_number}"
                resolved_sources[sid] = {
                    "source_id": sid,
                    "source_type": "github_pull_request",
                    "repository": pr.repository.full_name if pr.repository else "unknown",
                    "number": pr.pr_number,
                    "url": pr.html_url or "",
                    "content": content_text
                }

        return resolved_sources

    def verify_single_claim(
        self,
        claim_id: str,
        parent_claim_id: Optional[str],
        claim_text: str,
        source_ids: List[str],
        resolved_sources: Dict[str, Dict[str, Any]]
    ) -> ClaimVerificationResult:
        """
        Executes Two-Level Verification for an atomic claim against resolved sources.
        """
        is_critical, is_destructive = classify_claim_criticality(claim_text)

        # Level 1: Deterministic Evidence & Reference Validation
        missing_or_invalid_sources = [sid for sid in source_ids if sid not in resolved_sources]
        if not source_ids:
            return ClaimVerificationResult(
                claim_id=claim_id,
                parent_claim_id=parent_claim_id,
                claim_text=claim_text,
                verdict="UNSUPPORTED",
                support_strength=0.0,
                evidence_spans=[],
                source_ids=[],
                explanation="No source IDs were cited to support this claim.",
                is_critical=is_critical,
                is_destructive=is_destructive,
                verifier_model=settings.verifier_llm_model,
                verifier_prompt_version=settings.verifier_prompt_version
            )

        if missing_or_invalid_sources and len(missing_or_invalid_sources) == len(source_ids):
            return ClaimVerificationResult(
                claim_id=claim_id,
                parent_claim_id=parent_claim_id,
                claim_text=claim_text,
                verdict="UNCLEAR",
                support_strength=0.0,
                evidence_spans=[],
                source_ids=source_ids,
                explanation=f"Cited sources {missing_or_invalid_sources} could not be resolved from stored evidence.",
                is_critical=is_critical,
                is_destructive=is_destructive,
                verifier_model=settings.verifier_llm_model,
                verifier_prompt_version=settings.verifier_prompt_version
            )

        # Extract evidence snippets across available sources
        all_spans: List[EvidenceSpan] = []
        combined_source_content = []

        for sid in source_ids:
            if sid in resolved_sources:
                src_data = resolved_sources[sid]
                spans = extract_relevant_evidence_snippets(
                    claim_text=claim_text,
                    source_id=sid,
                    source_content=src_data["content"],
                    top_k=settings.verifier_snippet_top_k,
                    max_chars=settings.verifier_snippet_max_chars
                )
                all_spans.extend(spans)
                combined_source_content.append(f"SOURCE [{sid}]:\n{src_data['content'][:1500]}")

        combined_text = "\n\n".join(combined_source_content)

        # Check Cache
        cache_key = self._get_cache_key(claim_text, combined_text)
        if cache_key in self._verification_cache:
            cached_data = self._verification_cache[cache_key]
            return ClaimVerificationResult.model_validate(cached_data)

        # Level 2: Semantic Verification via Independent Verifier LLM
        prompt = (
            f"FACTUAL CLAIM TO VERIFY:\n\"{claim_text}\"\n\n"
            f"SOURCE EVIDENCE EXCERPTS:\n{combined_text}\n\n"
            "Evaluate whether the claim is supported by the evidence. "
            "Return structured JSON with keys: verdict, support_strength, explanation, evidence_spans."
        )

        try:
            llm_res = self.verifier_llm_client.generate_structured(
                prompt=prompt,
                system_prompt=VERIFIER_SYSTEM_PROMPT_V1,
                response_schema=LLMVerifierOutput
            )

            # Map raw fields cleanly
            verdict = llm_res.get("verdict", "UNCLEAR").upper()
            if verdict not in ["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "UNCLEAR"]:
                verdict = "UNCLEAR"

            support_strength = float(llm_res.get("support_strength", 0.0))

            res_obj = ClaimVerificationResult(
                claim_id=claim_id,
                parent_claim_id=parent_claim_id,
                claim_text=claim_text,
                verdict=verdict,
                support_strength=round(max(0.0, min(1.0, support_strength)), 4),
                evidence_spans=all_spans if all_spans else [EvidenceSpan(source_id=source_ids[0], text="No snippet", relevance_score=0.0)],
                source_ids=source_ids,
                explanation=llm_res.get("explanation", "Independent semantic verification complete."),
                is_critical=is_critical,
                is_destructive=is_destructive,
                verifier_model=settings.verifier_llm_model,
                verifier_prompt_version=settings.verifier_prompt_version
            )

            self._verification_cache[cache_key] = res_obj.model_dump()
            return res_obj

        except Exception as exc:
            logger.error(f"Error during semantic claim verification: {exc}")
            return ClaimVerificationResult(
                claim_id=claim_id,
                parent_claim_id=parent_claim_id,
                claim_text=claim_text,
                verdict="UNCLEAR",
                support_strength=0.0,
                evidence_spans=all_spans,
                source_ids=source_ids,
                explanation=f"Verifier failed: {exc}",
                is_critical=is_critical,
                is_destructive=is_destructive,
                verifier_model=settings.verifier_llm_model,
                verifier_prompt_version=settings.verifier_prompt_version
            )

    def verify_resolution(
        self,
        resolution_run_id: str,
        session: Session
    ) -> ResolutionVerificationSummary:
        """
        Main API entry point: Verifies all claims of a ResolutionRun.
        Determines aggregated resolution faithfulness status and persists audit record.
        """
        # Find ResolutionRun in database
        run_record = session.scalar(
            select(ResolutionRun).where(
                (ResolutionRun.run_id == resolution_run_id) | (ResolutionRun.id == int(resolution_run_id))
                if resolution_run_id.isdigit() else (ResolutionRun.run_id == resolution_run_id)
            )
        )

        if not run_record:
            raise ValueError(f"ResolutionRun with ID/run_id '{resolution_run_id}' not found in database.")

        raw_claims = run_record.claims
        if not raw_claims and run_record.raw_output:
            raw_claims_data = run_record.raw_output.get("claims", [])
        else:
            raw_claims_data = [{"claim_id": c.claim_id, "text": c.claim_text, "source_ids": c.source_ids} for c in raw_claims]

        # Collect all source IDs across claims
        all_cited_source_ids: List[str] = []
        for c in raw_claims_data:
            all_cited_source_ids.extend(c.get("source_ids", []))

        # Batch-fetch all source evidence from DB
        resolved_sources = self.batch_fetch_sources(all_cited_source_ids, session)

        # Decompose compound claims into atomic sub-claims & verify each
        verified_claim_results: List[ClaimVerificationResult] = []

        for c_dict in raw_claims_data:
            orig_id = c_dict.get("claim_id", "c0")
            orig_text = c_dict.get("text", "")
            s_ids = c_dict.get("source_ids", [])

            atomic_sub_claims = decompose_claim(orig_id, orig_text)

            for sub_id, parent_id, sub_text in atomic_sub_claims:
                res = self.verify_single_claim(
                    claim_id=sub_id,
                    parent_claim_id=parent_id,
                    claim_text=sub_text,
                    source_ids=s_ids,
                    resolved_sources=resolved_sources
                )
                verified_claim_results.append(res)

        # Count verdicts
        total_claims = len(verified_claim_results)
        supported_cnt = sum(1 for r in verified_claim_results if r.verdict == "SUPPORTED")
        partially_cnt = sum(1 for r in verified_claim_results if r.verdict == "PARTIALLY_SUPPORTED")
        unsupported_cnt = sum(1 for r in verified_claim_results if r.verdict == "UNSUPPORTED")
        contradicted_cnt = sum(1 for r in verified_claim_results if r.verdict == "CONTRADICTED")
        unclear_cnt = sum(1 for r in verified_claim_results if r.verdict == "UNCLEAR")

        # Check for critical failures
        has_critical_failure = False
        for r in verified_claim_results:
            if (r.is_critical or r.is_destructive) and r.verdict in ["UNSUPPORTED", "CONTRADICTED", "UNCLEAR"]:
                has_critical_failure = True
                break

        # Calculate Rates
        valid_sources_cnt = sum(1 for r in verified_claim_results if r.source_ids and all(s in resolved_sources for s in r.source_ids))
        citation_coverage = round(valid_sources_cnt / float(total_claims), 4) if total_claims > 0 else 0.0
        claim_support_rate = round((supported_cnt + 0.5 * partially_cnt) / float(total_claims), 4) if total_claims > 0 else 0.0
        strict_faithfulness = round(supported_cnt / float(total_claims), 4) if total_claims > 0 else 0.0
        unsupported_rate = round(unsupported_cnt / float(total_claims), 4) if total_claims > 0 else 0.0
        contradiction_rate = round(contradicted_cnt / float(total_claims), 4) if total_claims > 0 else 0.0
        partial_support_rate = round(partially_cnt / float(total_claims), 4) if total_claims > 0 else 0.0

        # Aggregated Resolution Status Rules
        if has_critical_failure or contradicted_cnt > 0:
            needs_human_review = True
            overall_status = "CONTRADICTED" if contradicted_cnt > 0 else "NEEDS_HUMAN_REVIEW"
        elif total_claims > 0 and supported_cnt == total_claims:
            needs_human_review = False
            overall_status = "FULLY_SUPPORTED"
        elif claim_support_rate >= 0.75:
            needs_human_review = False
            overall_status = "MOSTLY_SUPPORTED"
        elif claim_support_rate >= 0.40:
            needs_human_review = True
            overall_status = "PARTIALLY_SUPPORTED"
        else:
            needs_human_review = True
            overall_status = "UNSUPPORTED"

        now_utc = datetime.now(timezone.utc)
        ver_run_id = f"ver_{now_utc.strftime('%Y%m%d_%H%M%S_%f')[:20]}"

        summary = ResolutionVerificationSummary(
            verification_run_id=ver_run_id,
            resolution_run_id=run_record.run_id,
            overall_faithfulness_status=overall_status,
            total_claims=total_claims,
            supported_count=supported_cnt,
            partially_supported_count=partially_cnt,
            unsupported_count=unsupported_cnt,
            contradicted_count=contradicted_cnt,
            unclear_count=unclear_cnt,
            citation_coverage=citation_coverage,
            claim_support_rate=claim_support_rate,
            strict_faithfulness=strict_faithfulness,
            unsupported_claim_rate=unsupported_rate,
            contradiction_rate=contradiction_rate,
            partial_support_rate=partial_support_rate,
            needs_human_review=needs_human_review,
            has_critical_failure=has_critical_failure,
            claim_results=verified_claim_results
        )

        # Database Persistence
        ver_run_rec = VerificationRun(
            verification_run_id=ver_run_id,
            resolution_run_id=run_record.id,
            verifier_model=settings.verifier_llm_model,
            verifier_prompt_version=settings.verifier_prompt_version,
            overall_faithfulness_status=overall_status,
            total_claims=total_claims,
            supported_count=supported_cnt,
            partially_supported_count=partially_cnt,
            unsupported_count=unsupported_cnt,
            contradicted_count=contradicted_cnt,
            unclear_count=unclear_cnt,
            citation_coverage=citation_coverage,
            claim_support_rate=claim_support_rate,
            strict_faithfulness=strict_faithfulness,
            unsupported_claim_rate=unsupported_rate,
            contradiction_rate=contradiction_rate,
            needs_human_review=needs_human_review,
            has_critical_failure=has_critical_failure,
            verified_at=now_utc
        )
        session.add(ver_run_rec)
        session.flush()

        for cr in verified_claim_results:
            claim_rec = ClaimVerificationRecord(
                verification_run_id=ver_run_rec.id,
                claim_id=cr.claim_id,
                parent_claim_id=cr.parent_claim_id,
                claim_text=cr.claim_text,
                is_critical=cr.is_critical,
                is_destructive=cr.is_destructive,
                verdict=cr.verdict,
                support_strength=cr.support_strength,
                source_ids=cr.source_ids,
                evidence_spans=[s.model_dump() for s in cr.evidence_spans],
                explanation=cr.explanation,
                verified_at=now_utc
            )
            session.add(claim_rec)

        session.commit()

        # Artifact Storage
        artifact_dir = Path("artifacts/verification") / f"run_{ver_run_id}"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        with open(artifact_dir / "verification.json", "w", encoding="utf-8") as f:
            json.dump(summary.model_dump(), f, indent=2)

        with open(artifact_dir / "claim_results.json", "w", encoding="utf-8") as f:
            json.dump([cr.model_dump() for cr in verified_claim_results], f, indent=2)

        review_samples = [
            cr.model_dump() for cr in verified_claim_results
            if cr.verdict in ["UNSUPPORTED", "CONTRADICTED", "PARTIALLY_SUPPORTED", "UNCLEAR"] or cr.is_critical
        ]
        with open(artifact_dir / "review_samples.json", "w", encoding="utf-8") as f:
            json.dump(review_samples, f, indent=2)

        metrics = {
            "verification_run_id": ver_run_id,
            "resolution_run_id": run_record.run_id,
            "overall_status": overall_status,
            "strict_faithfulness": strict_faithfulness,
            "claim_support_rate": claim_support_rate,
            "citation_coverage": citation_coverage,
            "unsupported_claim_rate": unsupported_rate,
            "contradiction_rate": contradiction_rate,
            "partial_support_rate": partial_support_rate,
            "needs_human_review": needs_human_review,
            "has_critical_failure": has_critical_failure
        }
        with open(artifact_dir / "metrics.json", "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

        logger.info(f"Verification run complete: {ver_run_id}. Overall status: {overall_status}")
        return summary


def render_human_readable_verification(summary: ResolutionVerificationSummary) -> str:
    """Renders formatted human-readable claim verification report."""
    lines = []
    lines.append("===================================================================================")
    lines.append("                    CLAIM VERIFICATION / FAITHFULNESS REPORT                       ")
    lines.append("===================================================================================")
    lines.append(f"VERIFICATION RUN ID: {summary.verification_run_id}")
    lines.append(f"TARGET RESOLUTION:   {summary.resolution_run_id}")
    lines.append(f"OVERALL FAITHFULNESS:{summary.overall_faithfulness_status}")
    lines.append(f"HUMAN REVIEW NEEDED: {summary.needs_human_review}")
    lines.append(f"CRITICAL FAILURE:    {summary.has_critical_failure}")
    lines.append("-----------------------------------------------------------------------------------")
    lines.append(f"STRICT FAITHFULNESS: {summary.strict_faithfulness * 100:.1f}%")
    lines.append(f"CLAIM SUPPORT RATE:  {summary.claim_support_rate * 100:.1f}%")
    lines.append(f"CITATION COVERAGE:   {summary.citation_coverage * 100:.1f}%")
    lines.append(f"UNSUPPORTED RATE:    {summary.unsupported_claim_rate * 100:.1f}%")
    lines.append(f"CONTRADICTION RATE:  {summary.contradiction_rate * 100:.1f}%")
    lines.append("-----------------------------------------------------------------------------------")
    lines.append(f"TOTAL CLAIMS EVALUATED: {summary.total_claims}")
    lines.append(f"  - SUPPORTED:           {summary.supported_count}")
    lines.append(f"  - PARTIALLY SUPPORTED: {summary.partially_supported_count}")
    lines.append(f"  - UNSUPPORTED:         {summary.unsupported_count}")
    lines.append(f"  - CONTRADICTED:        {summary.contradicted_count}")
    lines.append(f"  - UNCLEAR:             {summary.unclear_count}")
    lines.append("-----------------------------------------------------------------------------------")
    lines.append("DETAILED CLAIM VERDICTS:")
    for cr in summary.claim_results:
        crit_tag = " [CRITICAL]" if cr.is_critical or cr.is_destructive else ""
        lines.append(f"\n  [{cr.claim_id}]{crit_tag} VERDICT: {cr.verdict} (Strength: {cr.support_strength})")
        lines.append(f"    Claim Text:  \"{cr.claim_text}\"")
        lines.append(f"    Source IDs:  {', '.join(cr.source_ids) if cr.source_ids else 'None'}")
        lines.append(f"    Explanation: {cr.explanation}")
        lines.append("    Evidence Spans:")
        for span in cr.evidence_spans:
            lines.append(f"      - [{span.source_id}] (Score: {span.relevance_score}): \"{span.text[:150]}...\"")
    lines.append("===================================================================================\n")
    return "\n".join(lines)
