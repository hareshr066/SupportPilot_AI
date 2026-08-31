import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from app.database.session import get_db
from app.database.models import SeverityPrediction
from app.ml.severity_dataset import format_severity_text
from app.ml.severity_model import SeverityTransformerModel

logger = logging.getLogger(__name__)


class SeverityPredictionResult(BaseModel):
    query_issue_id: Optional[int] = None
    predicted_label: str
    prediction_score: float = Field(..., description="Softmax confidence score (not calibrated)")
    model_name: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SeverityClassifierService:
    """
    Production Severity Inference Service.
    Predicts issue severity from title + body without requiring existing database record or ground truth.
    Supports persisting predictions to dedicated PostgreSQL severity_predictions table.
    """

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or settings.severity_model_path
        self._transformer_model: Optional[SeverityTransformerModel] = None

    @property
    def model(self) -> SeverityTransformerModel:
        """Lazy-loads trained model artifacts from model directory."""
        if self._transformer_model is None:
            if os.path.exists(self.model_path) and os.path.exists(os.path.join(self.model_path, "label_mapping.json")):
                logger.info(f"Loading trained severity model from '{self.model_path}'...")
                self._transformer_model = SeverityTransformerModel.load_model_artifacts(self.model_path)
            else:
                logger.warning(
                    f"Trained model artifacts not found at '{self.model_path}'. "
                    "Initializing fresh DistilBERT model instance."
                )
                self._transformer_model = SeverityTransformerModel(
                    model_name=settings.severity_model_name,
                    num_labels=2,
                    label_to_id={"low": 0, "high": 1},
                    id_to_label={0: "low", 1: "high"}
                )
                self._transformer_model.initialize_new_model()
        return self._transformer_model

    def predict_severity(self, title: str, body: str) -> SeverityPredictionResult:
        """
        Predicts severity directly from issue title and body.
        Does NOT require an existing database record, issue ID, comments, or resolution.
        """
        formatted_text = format_severity_text(title, body)
        pred_ids, scores = self.model.predict_probs([formatted_text])

        pred_id = pred_ids[0]
        score = scores[0]

        predicted_label = self.model.id_to_label.get(pred_id, f"label_{pred_id}")

        return SeverityPredictionResult(
            query_issue_id=None,
            predicted_label=predicted_label,
            prediction_score=round(float(score), 4),
            model_name=self.model.model_name
        )

    def predict_and_persist(
        self,
        title: str,
        body: str,
        issue_id: Optional[int] = None,
        db_session: Optional[Session] = None
    ) -> SeverityPredictionResult:
        """
        Predicts severity for issue and persists prediction record into `severity_predictions` PostgreSQL table.
        Does NOT modify or overwrite historical ground-truth issue labels.
        """
        res = self.predict_severity(title, body)
        res.query_issue_id = issue_id

        def _persist_with_session(session: Session):
            record = SeverityPrediction(
                issue_id=issue_id,
                model_name=res.model_name,
                predicted_label=res.predicted_label,
                prediction_score=res.prediction_score,
                created_at=datetime.now(timezone.utc)
            )
            session.add(record)
            session.commit()
            logger.info(f"Persisted severity prediction (label='{res.predicted_label}', score={res.prediction_score}) to database.")

        if db_session:
            _persist_with_session(db_session)
        else:
            with get_db() as session:
                _persist_with_session(session)

        return res
