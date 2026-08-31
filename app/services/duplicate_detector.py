import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from config import settings
from app.database.session import get_db
from app.database.models import Issue, IssueEmbedding, Repository
from app.services.embedding_service import EmbeddingService, build_issue_embedding_text

logger = logging.getLogger(__name__)


class CandidateIssue(BaseModel):
    issue_id: int
    issue_number: int
    title: str
    body: str
    repository_id: int
    created_at: Optional[datetime] = None
    similarity_score: float
    duplicate_of_issue_number: Optional[int] = None
    duplicate_detected: bool = False


class DuplicateDetectionResult(BaseModel):
    query_issue_id: Optional[int] = None
    query_issue_number: Optional[int] = None
    is_duplicate: bool = False
    matched_issue_id: Optional[int] = None
    matched_issue_number: Optional[int] = None
    retrieval_similarity: float = 0.0
    cross_encoder_score: float = 0.0
    candidates_considered: int = 0
    model_name: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DuplicateDetector:
    """
    Two-stage Duplicate Detection Service:
      Stage 1: Sentence-Transformer Embedding Retrieval (Bi-encoder + pgvector)
      Stage 2: Cross-Encoder Reranking & Verification
    """

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        cross_encoder_name: Optional[str] = None,
        threshold: Optional[float] = None,
        top_k: Optional[int] = None
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        self.cross_encoder_name = cross_encoder_name or settings.cross_encoder_model_name
        self.threshold = threshold if threshold is not None else settings.duplicate_threshold
        self.top_k = top_k or settings.duplicate_top_k
        self._cross_encoder = None

    @property
    def cross_encoder(self):
        """Lazy loader for cross-encoder model."""
        if self._cross_encoder is None:
            logger.info(f"Loading cross-encoder model: {self.cross_encoder_name}...")
            from sentence_transformers import CrossEncoder
            self._cross_encoder = CrossEncoder(self.cross_encoder_name)
            logger.info(f"Cross-encoder model {self.cross_encoder_name} loaded successfully.")
        return self._cross_encoder

    def find_similar_issues_for_text(
        self,
        title: str,
        body: str,
        repository_id: Optional[int] = None,
        top_k: Optional[int] = None,
        filter_before_created_at: Optional[datetime] = None,
        exclude_issue_id: Optional[int] = None,
        db_session: Optional[Session] = None
    ) -> List[CandidateIssue]:
        """
        Stage 1: Generates query vector and retrieves top-K candidate issues from PostgreSQL/pgvector.
        Supports repository scoping and temporal filtering to prevent data leakage.
        """
        k = top_k or self.top_k
        query_text = f"Title:\n{title.strip()}\n\nDescription:\n{body.strip()}"
        query_vector = self.embedding_service.generate_text_embedding(query_text)

        def _search_with_session(session: Session) -> List[CandidateIssue]:
            # Query issue_embeddings for the configured model_name
            model_name = self.embedding_service.model_name
            
            # Fetch embeddings & issues
            stmt = (
                select(IssueEmbedding, Issue)
                .join(Issue, IssueEmbedding.issue_id == Issue.id)
                .where(IssueEmbedding.model_name == model_name)
            )

            if repository_id is not None:
                stmt = stmt.where(Issue.repository_id == repository_id)

            if exclude_issue_id is not None:
                stmt = stmt.where(Issue.id != exclude_issue_id)

            if filter_before_created_at is not None:
                stmt = stmt.where(Issue.created_at < filter_before_created_at)

            results = session.execute(stmt).all()
            if not results:
                return []

            # Compute cosine similarities
            scored_candidates: List[Tuple[float, Issue]] = []
            for emb_record, issue in results:
                emb_vector = emb_record.embedding
                # Compute cosine similarity
                sim = self._cosine_similarity(query_vector, emb_vector)
                scored_candidates.append((sim, issue))

            # Sort descending by similarity
            scored_candidates.sort(key=lambda x: x[0], reverse=True)

            candidates: List[CandidateIssue] = []
            for sim, issue in scored_candidates[:k]:
                candidates.append(
                    CandidateIssue(
                        issue_id=issue.id,
                        issue_number=issue.issue_number,
                        title=issue.title,
                        body=issue.body,
                        repository_id=issue.repository_id,
                        created_at=issue.created_at,
                        similarity_score=float(sim),
                        duplicate_of_issue_number=issue.duplicate_of_issue_number,
                        duplicate_detected=issue.duplicate_detected
                    )
                )

            return candidates

        if db_session:
            return _search_with_session(db_session)
        else:
            with get_db() as session:
                return _search_with_session(session)

    def find_similar_issues(
        self,
        issue_id: int,
        repository_id: Optional[int] = None,
        top_k: Optional[int] = None,
        exclude_self: bool = True,
        filter_before_created_at: Optional[datetime] = None,
        db_session: Optional[Session] = None
    ) -> List[CandidateIssue]:
        """
        Retrieves Stage 1 similarity candidates for an existing issue.
        Excludes the query issue itself to prevent self-retrieval leakage.
        """
        def _get_issue_and_search(session: Session) -> List[CandidateIssue]:
            issue = session.scalar(select(Issue).where(Issue.id == issue_id))
            if not issue:
                raise ValueError(f"Issue ID {issue_id} not found in database.")

            repo_id = repository_id or issue.repository_id
            exclude_id = issue_id if exclude_self else None

            return self.find_similar_issues_for_text(
                title=issue.title,
                body=issue.body,
                repository_id=repo_id,
                top_k=top_k,
                filter_before_created_at=filter_before_created_at,
                exclude_issue_id=exclude_id,
                db_session=session
            )

        if db_session:
            return _get_issue_and_search(db_session)
        else:
            with get_db() as session:
                return _get_issue_and_search(session)

    def detect_duplicate(
        self,
        title: str,
        body: str,
        repository_id: Optional[int] = None,
        query_issue_id: Optional[int] = None,
        query_issue_number: Optional[int] = None,
        filter_before_created_at: Optional[datetime] = None,
        custom_threshold: Optional[float] = None,
        db_session: Optional[Session] = None
    ) -> DuplicateDetectionResult:
        """
        Full Two-Stage Pipeline:
          Stage 1: Retrieve top-K candidates via embedding search.
          Stage 2: Rerank top-K candidates via Cross-Encoder.
          Decision: If top cross-encoder score >= threshold -> is_duplicate = True.
        """
        t_thresh = custom_threshold if custom_threshold is not None else self.threshold

        # Stage 1: Retrieval
        candidates = self.find_similar_issues_for_text(
            title=title,
            body=body,
            repository_id=repository_id,
            top_k=self.top_k,
            filter_before_created_at=filter_before_created_at,
            exclude_issue_id=query_issue_id,
            db_session=db_session
        )

        if not candidates:
            return DuplicateDetectionResult(
                query_issue_id=query_issue_id,
                query_issue_number=query_issue_number,
                is_duplicate=False,
                candidates_considered=0,
                model_name=f"{self.embedding_service.model_name} + {self.cross_encoder_name}"
            )

        query_text = f"Title:\n{title.strip()}\n\nDescription:\n{body.strip()}"

        # Stage 2: Cross-Encoder Reranking
        pairs = []
        for cand in candidates:
            cand_text = f"Title:\n{cand.title.strip()}\n\nDescription:\n{cand.body.strip()}"
            pairs.append((query_text, cand_text))

        # Compute cross-encoder scores
        scores = self.cross_encoder.predict(pairs, show_progress_bar=False)

        # Rank candidates by cross-encoder score descending
        scored_pairs = []
        for cand, score in zip(candidates, scores):
            scored_pairs.append((float(score), cand))

        scored_pairs.sort(key=lambda x: x[0], reverse=True)

        top_score, top_candidate = scored_pairs[0]
        is_dup = top_score >= t_thresh

        return DuplicateDetectionResult(
            query_issue_id=query_issue_id,
            query_issue_number=query_issue_number,
            is_duplicate=is_dup,
            matched_issue_id=top_candidate.issue_id if is_dup else None,
            matched_issue_number=top_candidate.issue_number if is_dup else None,
            retrieval_similarity=top_candidate.similarity_score,
            cross_encoder_score=top_score,
            candidates_considered=len(candidates),
            model_name=f"{self.embedding_service.model_name} + {self.cross_encoder_name}"
        )

    def _cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Computes dot product cosine similarity for normalized vectors."""
        if not vec_a or not vec_b:
            return 0.0
        # For normalized vectors, cosine similarity is the dot product
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        return float(dot)
