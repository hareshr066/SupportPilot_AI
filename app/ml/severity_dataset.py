import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import Issue, Repository, Label

logger = logging.getLogger(__name__)


class SeverityExample(BaseModel):
    issue_id: int
    repository_id: int
    created_at: datetime
    title: str
    body: str
    text: str
    target_label: str
    target_id: int


class DatasetSplit(BaseModel):
    train_examples: List[SeverityExample]
    val_examples: List[SeverityExample]
    test_examples: List[SeverityExample]
    label_to_id: Dict[str, int]
    id_to_label: Dict[int, str]
    date_ranges: Dict[str, Dict[str, Any]]
    ambiguous_excluded_count: int = 0
    unlabeled_excluded_count: int = 0


def format_severity_text(title: str, body: str) -> str:
    """
    Constructs model input text cleanly formatted with Title preserved.
    Strictly excludes IDs, resolution, PRs, comments, and ground-truth fields.
    """
    clean_title = (title or "").strip()
    clean_body = (body or "").strip()
    return f"Title:\n{clean_title}\n\nDescription:\n{clean_body}"


def prepare_severity_dataset(
    repository_id: int,
    valid_severity_labels: List[str],
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    db_session: Optional[Session] = None
) -> DatasetSplit:
    """
    Constructs supervised severity dataset from PostgreSQL Silver issues.
    Features:
      - Maps specified valid severity labels to integer target IDs.
      - Excludes unlabeled issues and ambiguous issues with multiple conflicting severity labels.
      - Applies strict temporal split (chronological train/val/test) to prevent data leakage.
    """
    def _fetch_and_build(session: Session) -> DatasetSplit:
        # Fetch issues for repository sorted chronologically by created_at
        stmt = (
            select(Issue)
            .where(Issue.repository_id == repository_id)
            .order_by(Issue.created_at.asc())
        )
        issues = session.scalars(stmt).all()

        # Build label mapping dictionary
        sorted_labels = sorted(list(set(valid_severity_labels)))
        label_to_id = {label: i for i, label in enumerate(sorted_labels)}
        id_to_label = {i: label for i, label in enumerate(sorted_labels)}

        valid_set = set(valid_severity_labels)

        examples: List[SeverityExample] = []
        ambiguous_count = 0
        unlabeled_count = 0

        for issue in issues:
            # Extract labels attached to issue
            issue_label_names = [label.name for label in issue.labels]
            matched_severity = [name for name in issue_label_names if name in valid_set]

            if len(matched_severity) == 0:
                unlabeled_count += 1
                continue
            elif len(matched_severity) > 1:
                # Ambiguous: multiple conflicting severity labels attached
                ambiguous_count += 1
                logger.warning(
                    f"Issue ID {issue.id} (#{issue.issue_number}) has conflicting severity labels: "
                    f"{matched_severity}. Excluding from supervised training dataset."
                )
                continue

            target_str = matched_severity[0]
            target_int = label_to_id[target_str]
            formatted_text = format_severity_text(issue.title, issue.body)

            examples.append(
                SeverityExample(
                    issue_id=issue.id,
                    repository_id=issue.repository_id,
                    created_at=issue.created_at,
                    title=issue.title,
                    body=issue.body,
                    text=formatted_text,
                    target_label=target_str,
                    target_id=target_int
                )
            )

        total_examples = len(examples)
        if total_examples == 0:
            logger.warning(f"No valid severity examples found for repository_id={repository_id}.")
            return DatasetSplit(
                train_examples=[],
                val_examples=[],
                test_examples=[],
                label_to_id=label_to_id,
                id_to_label=id_to_label,
                date_ranges={"train": {}, "val": {}, "test": {}},
                ambiguous_excluded_count=ambiguous_count,
                unlabeled_excluded_count=unlabeled_count
            )

        # Compute temporal split boundaries
        n_train = int(total_examples * train_ratio)
        n_val = int(total_examples * val_ratio)

        train_set = examples[:n_train]
        val_set = examples[n_train: n_train + n_val]
        test_set = examples[n_train + n_val:]

        date_ranges = {
            "train": {
                "start": train_set[0].created_at.isoformat() if train_set else None,
                "end": train_set[-1].created_at.isoformat() if train_set else None,
                "count": len(train_set)
            },
            "val": {
                "start": val_set[0].created_at.isoformat() if val_set else None,
                "end": val_set[-1].created_at.isoformat() if val_set else None,
                "count": len(val_set)
            },
            "test": {
                "start": test_set[0].created_at.isoformat() if test_set else None,
                "end": test_set[-1].created_at.isoformat() if test_set else None,
                "count": len(test_set)
            }
        }

        return DatasetSplit(
            train_examples=train_set,
            val_examples=val_set,
            test_examples=test_set,
            label_to_id=label_to_id,
            id_to_label=id_to_label,
            date_ranges=date_ranges,
            ambiguous_excluded_count=ambiguous_count,
            unlabeled_excluded_count=unlabeled_count
        )

    if db_session:
        return _fetch_and_build(db_session)
    else:
        with get_db() as session:
            return _fetch_and_build(session)
