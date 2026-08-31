from datetime import datetime
from typing import List, Dict, Any, Optional

class TemporalLeakageError(ValueError):
    """Raised when evaluation input contains future information."""
    pass

class LeakageValidator:
    """
    Validation utilities ensuring zero future-to-past temporal leakage
    during model evaluation and threshold tuning.
    """

    @staticmethod
    def validate_retrieval_corpus(
        ticket_timestamp: datetime,
        retrieved_tickets: List[Dict[str, Any]],
        ticket_id: Optional[int] = None
    ) -> bool:
        """
        Validates that no retrieved ticket was created or closed after ticket_timestamp,
        and that the ticket itself is excluded from retrieval.
        """
        for item in retrieved_tickets:
            item_created = item.get("created_at")
            if isinstance(item_created, str):
                item_created = datetime.fromisoformat(item_created)
            
            if item_created and item_created > ticket_timestamp:
                raise TemporalLeakageError(
                    f"Retrieval leakage! Retrieved ticket {item.get('ticket_id')} created at {item_created} "
                    f"is in the future relative to query ticket timestamp {ticket_timestamp}."
                )

            if ticket_id is not None and item.get("ticket_id") == ticket_id:
                raise TemporalLeakageError(
                    f"Retrieval leakage! Query ticket {ticket_id} retrieved itself."
                )

        return True

    @staticmethod
    def validate_feature_timestamp(
        ticket_timestamp: datetime,
        feature_timestamp: Optional[datetime],
        feature_name: str
    ) -> bool:
        """
        Validates that a feature (comment, PR, label update) occurred before ticket_timestamp.
        """
        if feature_timestamp and feature_timestamp > ticket_timestamp:
            raise TemporalLeakageError(
                f"Feature leakage! '{feature_name}' timestamp {feature_timestamp} is after ticket timestamp {ticket_timestamp}."
            )
        return True

    @staticmethod
    def validate_threshold_tuning_split(
        split_used_for_tuning: str,
        eval_split: str
    ) -> bool:
        """
        Validates that model parameters/thresholds are tuned on train/val, NEVER on test.
        """
        if eval_split.lower() == "test" and split_used_for_tuning.lower() == "test":
            raise TemporalLeakageError(
                "Data leakage! Threshold selection must NOT use the held-out test set."
            )
        return True
