import os
import json
import logging
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Set

from sqlalchemy.orm import Session
from sqlalchemy import select

from config import settings
from app.database.session import get_db
from app.database.models import (
    Issue,
    Repository,
    Label,
    Comment,
    PullRequest,
    IssueEmbedding,
    RetrievalIndexMetadata,
    RootCauseAssignment,
)
from app.services.embedding_service import EmbeddingService
from app.services.bm25_service import BM25Index, tokenize_technical_text

logger = logging.getLogger(__name__)

RESOLUTION_KEYWORDS = {
    "fix", "fixed", "resolv", "resolved", "close", "closed", "solv", "solution",
    "patch", "merged", "pr", "pull request", "workaround", "commit"
}


def build_canonical_text(
    title: str,
    body: str,
    labels: List[str],
    comments: List[str],
    pr_titles: List[str]
) -> str:
    """
    Constructs a canonical text representation for lexical and document retrieval.
    Sensibly truncates large comment streams and PR bodies to preserve key resolution evidence.
    """
    clean_title = (title or "").strip()
    clean_body = (body or "").strip()
    labels_str = ", ".join(labels) if labels else ""

    # Truncate comments: take up to 3 most relevant/closing comments, max 300 chars each
    truncated_comments = []
    for c in comments[-3:]:
        c_clean = (c or "").strip()
        if c_clean:
            truncated_comments.append(c_clean[:300])
    comments_str = "\n".join(truncated_comments)

    # Truncate PR titles
    prs_str = ", ".join(pr_titles) if pr_titles else ""

    canonical = (
        f"TITLE:\n{clean_title}\n\n"
        f"BODY:\n{clean_body[:1000]}\n\n"
        f"LABELS:\n{labels_str}\n\n"
        f"COMMENTS:\n{comments_str}\n\n"
        f"PULL REQUESTS / RESOLUTION:\n{prs_str}"
    )
    return canonical.strip()


def calculate_resolution_evidence(
    has_comments: bool,
    has_prs: bool,
    comments_text: str,
    pr_text: str,
    state_reason: Optional[str] = None
) -> Tuple[float, Dict[str, bool]]:
    """
    Calculates resolution-evidence completeness score based on historical issue resolution artifacts.
    """
    comb_text = f"{comments_text} {pr_text}".lower()
    has_res_text = any(kw in comb_text for kw in RESOLUTION_KEYWORDS)
    has_fix_ref = bool(
        has_prs or
        (state_reason and state_reason.lower() in ["completed", "not_planned"]) or
        ("fix" in comb_text or "patch" in comb_text)
    )

    flags = {
        "has_closing_comment": has_comments,
        "has_linked_pr": has_prs,
        "has_resolution_text": has_res_text,
        "has_fix_reference": has_fix_ref,
    }

    # Evidence score calculation: weighted combination
    score = (
        0.3 * float(has_comments) +
        0.3 * float(has_prs) +
        0.2 * float(has_res_text) +
        0.2 * float(has_fix_ref)
    )
    return round(score, 4), flags


class HybridRetrievalService:
    """
    Hybrid Resolution-Relevant Retrieval Engine.
    Combines pgvector Dense Semantic Search + BM25 Technical Lexical Search via RRF.
    Applies resolution-evidence aware reranking to prioritize historical resolved cases.
    """

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        db_session: Optional[Session] = None,
        bm25_index_dir: Optional[str] = None
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        self._external_session = db_session
        self.bm25_index_dir = Path(bm25_index_dir or settings.retrieval_bm25_index_dir)
        self.bm25_index: Optional[BM25Index] = None

    def load_or_build_bm25_index(
        self,
        session: Session,
        repository_id: Optional[int] = None,
        force_rebuild: bool = False
    ) -> BM25Index:
        """Loads persistent BM25 index from disk or builds it if not cached or force_rebuild is True."""
        idx_file = self.bm25_index_dir / "bm25_index.json"
        if idx_file.exists() and not force_rebuild:
            try:
                self.bm25_index = BM25Index.load(idx_file)
                return self.bm25_index
            except Exception as e:
                logger.warning(f"Failed to load cached BM25 index: {e}. Rebuilding...")

        self.build_retrieval_index(session, repository_id=repository_id)
        return self.bm25_index

    def build_retrieval_index(
        self,
        session: Session,
        repository_id: Optional[int] = None,
        index_version: str = "v1"
    ) -> Dict[str, Any]:
        """
        Phase 25 & 26: Builds canonical document representations for historical resolved issues
        and persists the BM25 index and metadata.
        """
        query = select(Issue).where(Issue.state == "closed")
        if repository_id is not None:
            query = query.where(Issue.repository_id == repository_id)

        closed_issues = session.scalars(query).all()

        # Fallback if no closed issues found (e.g. dev dataset)
        if not closed_issues:
            logger.warning("No closed issues found for BM25 index building. Using all available issues.")
            query_all = select(Issue)
            if repository_id is not None:
                query_all = query_all.where(Issue.repository_id == repository_id)
            closed_issues = session.scalars(query_all).all()

        canonical_docs = []
        for issue in closed_issues:
            labels = [l.name for l in issue.labels]
            comments = [c.body for c in issue.comments]
            pr_titles = [pr.html_url or f"PR #{pr.pr_number}" for pr in issue.pull_requests]

            canonical_text = build_canonical_text(
                title=issue.title,
                body=issue.body,
                labels=labels,
                comments=comments,
                pr_titles=pr_titles
            )

            canonical_docs.append({
                "issue_id": issue.id,
                "canonical_text": canonical_text
            })

        self.bm25_index = BM25Index()
        self.bm25_index.fit(canonical_docs)

        # Save to disk
        self.bm25_index_dir.mkdir(parents=True, exist_ok=True)
        idx_file = self.bm25_index_dir / "bm25_index.json"
        self.bm25_index.save(idx_file)

        # Persist index metadata in PostgreSQL
        now_utc = datetime.now(timezone.utc)
        meta_record = session.scalar(
            select(RetrievalIndexMetadata).where(RetrievalIndexMetadata.index_version == index_version)
        )
        if not meta_record:
            meta_record = RetrievalIndexMetadata(
                index_version=index_version,
                repository_id=repository_id,
                document_count=len(canonical_docs),
                embedding_model=self.embedding_service.model_name,
                bm25_params={"k1": self.bm25_index.k1, "b": self.bm25_index.b},
                build_timestamp=now_utc,
                index_path=str(idx_file)
            )
            session.add(meta_record)
        else:
            meta_record.document_count = len(canonical_docs)
            meta_record.build_timestamp = now_utc

        session.flush()
        logger.info(f"Retrieval index built successfully with {len(canonical_docs)} documents.")

        return {
            "index_version": index_version,
            "document_count": len(canonical_docs),
            "index_path": str(idx_file),
            "build_timestamp": now_utc.isoformat()
        }

    def retrieve_dense(
        self,
        query_embedding: List[float],
        session: Session,
        repository_id: Optional[int] = None,
        top_k: int = 50,
        temporal_cutoff: Optional[datetime] = None
    ) -> List[Tuple[int, float]]:
        """
        Dense Semantic Retrieval via vector similarity.
        Uses pgvector L2 / cosine distance when available, or vector matrix dot product.
        """
        model_name = self.embedding_service.model_name
        q = select(IssueEmbedding, Issue).join(Issue, IssueEmbedding.issue_id == Issue.id).where(
            IssueEmbedding.model_name == model_name
        )

        if repository_id is not None and settings.retrieval_repository_scope == "same_repository":
            q = q.where(Issue.repository_id == repository_id)

        # Temporal filtering constraint: candidate.closed_at < temporal_cutoff
        if temporal_cutoff is not None:
            q = q.where(Issue.created_at < temporal_cutoff)

        rows = session.execute(q).all()
        if not rows:
            return []

        query_vec = np.array(query_embedding, dtype=np.float32)
        norm_q = np.linalg.norm(query_vec)
        if norm_q > 0:
            query_vec = query_vec / norm_q

        scored_candidates = []
        for emb_obj, issue_obj in rows:
            emb_raw = emb_obj.embedding
            if not emb_raw:
                continue
            doc_vec = np.array(emb_raw, dtype=np.float32)
            norm_d = np.linalg.norm(doc_vec)
            if norm_d > 0:
                doc_vec = doc_vec / norm_d

            # Cosine similarity
            sim = float(np.dot(query_vec, doc_vec))
            scored_candidates.append((issue_obj.id, sim))

        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        return scored_candidates[:top_k]

    def retrieve_bm25(
        self,
        query_text: str,
        session: Session,
        repository_id: Optional[int] = None,
        top_k: int = 50,
        temporal_cutoff: Optional[datetime] = None
    ) -> List[Tuple[int, float]]:
        """Lexical retrieval using persistent BM25 index."""
        if self.bm25_index is None:
            self.load_or_build_bm25_index(session, repository_id=repository_id)

        # Determine eligible document IDs based on repo scope & temporal constraint
        q = select(Issue.id)
        if repository_id is not None and settings.retrieval_repository_scope == "same_repository":
            q = q.where(Issue.repository_id == repository_id)
        if temporal_cutoff is not None:
            q = q.where(Issue.created_at < temporal_cutoff)

        eligible_ids = set(session.scalars(q).all())
        return self.bm25_index.search(query_text, top_k=top_k, eligible_doc_ids=eligible_ids)

    def retrieve_resolved_cases(
        self,
        query_text: str,
        repository_id: Optional[int] = None,
        query_issue_id: Optional[int] = None,
        top_k: Optional[int] = None,
        temporal_cutoff: Optional[datetime] = None,
        db_session: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes end-to-end Hybrid Resolution-Relevant Retrieval.
        Combines Dense + BM25 via Reciprocal Rank Fusion (RRF) and applies evidence reranking.
        """
        target_top_k = top_k or settings.retrieval_final_top_k
        dense_k = settings.retrieval_dense_top_k
        bm25_k = settings.retrieval_bm25_top_k
        rrf_k = settings.retrieval_rrf_k
        w_dense = settings.retrieval_dense_weight
        w_bm25 = settings.retrieval_bm25_weight
        alpha_ev = settings.retrieval_alpha_evidence

        def _execute(session: Session) -> List[Dict[str, Any]]:
            # Generate query embedding
            query_emb = self.embedding_service.generate_text_embedding(query_text)

            # 1. Dense Semantic Retrieval
            dense_results = self.retrieve_dense(
                query_emb, session, repository_id=repository_id, top_k=dense_k, temporal_cutoff=temporal_cutoff
            )

            # 2. BM25 Lexical Retrieval
            bm25_results = self.retrieve_bm25(
                query_text, session, repository_id=repository_id, top_k=bm25_k, temporal_cutoff=temporal_cutoff
            )

            # Map ranks
            dense_rank_map = {issue_id: rank + 1 for rank, (issue_id, score) in enumerate(dense_results)}
            dense_score_map = {issue_id: score for issue_id, score in dense_results}

            bm25_rank_map = {issue_id: rank + 1 for rank, (issue_id, score) in enumerate(bm25_results)}
            bm25_score_map = {issue_id: score for issue_id, score in bm25_results}

            # 3. Deduplicated Union of Candidate IDs
            candidate_ids = set(dense_rank_map.keys()).union(set(bm25_rank_map.keys()))

            # Exclude the query issue itself if query_issue_id is provided
            if query_issue_id is not None:
                candidate_ids.discard(query_issue_id)

            if not candidate_ids:
                return []

            # Retrieve candidate Issue objects from DB
            issues_q = select(Issue).where(Issue.id.in_(candidate_ids))
            candidate_issues = {iss.id: iss for iss in session.scalars(issues_q).all()}

            scored_candidates = []
            penalty_rank = 1000

            for issue_id in candidate_ids:
                iss = candidate_issues.get(issue_id)
                if not iss:
                    continue

                d_rank = dense_rank_map.get(issue_id, penalty_rank)
                b_rank = bm25_rank_map.get(issue_id, penalty_rank)

                d_score = dense_score_map.get(issue_id, 0.0)
                b_score = bm25_score_map.get(issue_id, 0.0)

                # Reciprocal Rank Fusion (RRF) calculation
                rrf_score = (
                    w_dense * (1.0 / (rrf_k + d_rank)) +
                    w_bm25 * (1.0 / (rrf_k + b_rank))
                )

                # Calculate Resolution Evidence completeness score
                comments_text = " ".join([c.body for c in iss.comments])
                pr_titles = " ".join([pr.html_url or f"PR #{pr.pr_number}" for pr in iss.pull_requests])
                
                ev_score, ev_flags = calculate_resolution_evidence(
                    has_comments=len(iss.comments) > 0,
                    has_prs=len(iss.pull_requests) > 0,
                    comments_text=comments_text,
                    pr_text=pr_titles,
                    state_reason=iss.state_reason
                )

                # Final score: Relevance RRF score boosted by resolution evidence factor
                final_score = rrf_score * (1.0 + alpha_ev * ev_score)

                # Extract solution snippet
                snippet = comments_text[:300] if comments_text else iss.body[:300]

                pr_urls = [pr.html_url for pr in iss.pull_requests if pr.html_url]

                scored_candidates.append({
                    "issue_id": iss.id,
                    "issue_number": iss.issue_number,
                    "repository": iss.repository.full_name if iss.repository else "",
                    "repository_id": iss.repository_id,
                    "title": iss.title,
                    "url": iss.html_url,
                    "state": iss.state,
                    "closed_at": iss.closed_at.isoformat() if iss.closed_at else None,
                    "dense_score": round(float(d_score), 4),
                    "dense_rank": d_rank if d_rank != penalty_rank else None,
                    "bm25_score": round(float(b_score), 4),
                    "bm25_rank": b_rank if b_rank != penalty_rank else None,
                    "rrf_score": round(float(rrf_score), 6),
                    "evidence_score": round(float(ev_score), 4),
                    "final_score": round(float(final_score), 6),
                    "resolution_evidence": ev_flags,
                    "resolution_text_snippet": snippet,
                    "source_references": {
                        "issue_url": iss.html_url,
                        "pr_urls": pr_urls
                    }
                })

            # Sort by final score descending
            scored_candidates.sort(key=lambda x: x["final_score"], reverse=True)
            return scored_candidates[:target_top_k]

        if db_session:
            return _execute(db_session)
        elif self._external_session:
            return _execute(self._external_session)
        else:
            with get_db() as session:
                return _execute(session)
