import logging
from datetime import datetime, timezone
from typing import List, Optional, Union, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select

from config import settings
from app.database.session import get_db
from app.database.models import Issue, IssueEmbedding

logger = logging.getLogger(__name__)


def build_issue_embedding_text(issue: Union[Issue, Dict[str, Any]]) -> str:
    """
    Deterministically builds the embedding input text for an issue.
    
    Structure:
      Title: <title>
      Description: <body>
      Labels: <comma-separated labels>
      
    CRITICAL: Excludes ground-truth duplicate fields (duplicate_of_issue_number),
    database IDs, and ingestion timestamps to prevent data leakage.
    """
    if isinstance(issue, dict):
        title = issue.get("title", "") or ""
        body = issue.get("body", "") or ""
        raw_labels = issue.get("labels", []) or []
        if isinstance(raw_labels, list):
            label_names = [l.get("name", "") if isinstance(l, dict) else str(l) for l in raw_labels]
        else:
            label_names = []
    else:
        title = issue.title or ""
        body = issue.body or ""
        label_names = [label.name for label in getattr(issue, "labels", [])]

    # Clean text components
    clean_title = title.strip()
    clean_body = body.strip()
    labels_str = ", ".join(sorted(filter(None, label_names)))

    parts = [f"Title:\n{clean_title}"]
    if clean_body:
        parts.append(f"Description:\n{clean_body}")
    if labels_str:
        parts.append(f"Labels:\n{labels_str}")

    return "\n\n".join(parts)


class EmbeddingService:
    """
    Service responsible for loading sentence-transformer models,
    generating deterministic issue text embeddings, and persisting
    vector representations into PostgreSQL.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.embedding_model_name
        self._model = None

    @property
    def model(self):
        """Lazy loader for sentence-transformer model."""
        if self._model is None:
            logger.info(f"Loading embedding model: {self.model_name}...")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Embedding model {self.model_name} loaded successfully.")
        return self._model

    def get_embedding_dimension(self) -> int:
        """Returns vector embedding dimension programmatically."""
        return self.model.get_sentence_embedding_dimension()

    def generate_text_embedding(self, text: str) -> List[float]:
        """
        Generates a normalized float vector for input text.
        """
        if not text or not text.strip():
            # Return zero vector of model dimension for empty string
            return [0.0] * self.get_embedding_dimension()

        vector = self.model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vector.tolist()

    def generate_issue_embedding(self, issue: Union[Issue, Dict[str, Any]]) -> List[float]:
        """
        Generates an embedding vector for an issue entity or dict.
        """
        text = build_issue_embedding_text(issue)
        return self.generate_text_embedding(text)

    def generate_embeddings_for_repository(
        self,
        repository_id: int,
        db_session: Optional[Session] = None,
        batch_size: Optional[int] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Generates and persists embeddings for all issues belonging to repository_id.
        Processes issues in batches and skips existing embeddings unless force=True.
        """
        bsize = batch_size or settings.embedding_batch_size
        logger.info(
            f"Starting batch embedding generation for repository_id={repository_id} "
            f"using model={self.model_name} (batch_size={bsize})"
        )

        def _process_with_session(session: Session) -> Dict[str, Any]:
            # Fetch all issue IDs for this repository
            all_issues = session.scalars(
                select(Issue).where(Issue.repository_id == repository_id)
            ).all()

            total_issues = len(all_issues)
            if total_issues == 0:
                logger.info(f"No issues found for repository_id={repository_id}.")
                return {"total_issues": 0, "embedded": 0, "skipped": 0}

            # Pre-fetch existing embedding issue IDs for this model
            existing_embeddings = set(
                session.scalars(
                    select(IssueEmbedding.issue_id).where(
                        IssueEmbedding.model_name == self.model_name
                    )
                ).all()
            )

            issues_to_process = []
            skipped_count = 0

            for issue in all_issues:
                if not force and issue.id in existing_embeddings:
                    skipped_count += 1
                else:
                    issues_to_process.append(issue)

            logger.info(
                f"Repository contains {total_issues} issues. "
                f"To process: {len(issues_to_process)}, Skipped: {skipped_count}."
            )

            embedded_count = 0
            now_utc = datetime.now(timezone.utc)

            # Process in batches
            for i in range(0, len(issues_to_process), bsize):
                batch = issues_to_process[i : i + bsize]
                texts = [build_issue_embedding_text(issue) for issue in batch]

                # Generate batch embeddings
                vectors = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

                for issue, vec in zip(batch, vectors):
                    vec_list = vec.tolist()
                    existing_emb = session.scalar(
                        select(IssueEmbedding).where(
                            IssueEmbedding.issue_id == issue.id,
                            IssueEmbedding.model_name == self.model_name
                        )
                    )
                    if existing_emb:
                        existing_emb.embedding = vec_list
                        existing_emb.updated_at = now_utc
                    else:
                        emb_entity = IssueEmbedding(
                            issue_id=issue.id,
                            model_name=self.model_name,
                            embedding=vec_list,
                            created_at=now_utc,
                            updated_at=now_utc
                        )
                        session.add(emb_entity)
                    embedded_count += 1

                session.flush()
                logger.info(f"Embedded issues: {embedded_count} / {len(issues_to_process)}")

            return {
                "total_issues": total_issues,
                "embedded": embedded_count,
                "skipped": skipped_count
            }

        if db_session:
            return _process_with_session(db_session)
        else:
            with get_db() as session:
                return _process_with_session(session)
