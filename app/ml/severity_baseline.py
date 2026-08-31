import logging
from typing import List, Dict, Tuple, Any, Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, precision_recall_fscore_support

from app.ml.severity_dataset import SeverityExample

logger = logging.getLogger(__name__)


class SeverityBaselineModel:
    """
    TF-IDF + Logistic Regression Baseline Model for Severity Classification.
    Evaluated on the exact same temporal test split as Transformer models.
    """

    def __init__(self, max_features: int = 5000, random_state: int = 42):
        self.vectorizer = TfidfVectorizer(max_features=max_features, stop_words="english")
        self.classifier = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=random_state)
        self.is_trained = False

    def train(self, train_examples: List[SeverityExample]) -> None:
        """Fits TF-IDF vectorizer and Logistic Regression classifier on training set."""
        if not train_examples:
            raise ValueError("Cannot train baseline model on empty training set.")

        texts = [ex.text for ex in train_examples]
        labels = [ex.target_id for ex in train_examples]

        X_train = self.vectorizer.fit_transform(texts)
        self.classifier.fit(X_train, labels)
        self.is_trained = True
        logger.info(f"Baseline TF-IDF + LogisticRegression model trained on {len(train_examples)} examples.")

    def predict(self, texts: List[str]) -> Tuple[List[int], List[float]]:
        """Predicts class IDs and probabilities for input texts."""
        if not self.is_trained:
            raise RuntimeError("Baseline model has not been trained yet.")

        X = self.vectorizer.transform(texts)
        preds = self.classifier.predict(X).tolist()
        probs = self.classifier.predict_proba(X)
        scores = [float(np.max(prob)) for prob in probs]
        return preds, scores

    def evaluate(
        self,
        test_examples: List[SeverityExample],
        id_to_label: Dict[int, str]
    ) -> Dict[str, Any]:
        """Evaluates baseline model on test set and computes precision, recall, macro F1, weighted F1, confusion matrix."""
        if not test_examples:
            return {
                "accuracy": 0.0,
                "macro_precision": 0.0,
                "macro_recall": 0.0,
                "macro_f1": 0.0,
                "weighted_f1": 0.0,
                "per_class": {},
                "confusion_matrix": []
            }

        texts = [ex.text for ex in test_examples]
        y_true = [ex.target_id for ex in test_examples]

        y_pred, _ = self.predict(texts)

        acc = float(accuracy_score(y_true, y_pred))
        p_macro, r_macro, f1_macro, _ = precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)
        _, _, f1_weighted, _ = precision_recall_fscore_support(y_true, y_pred, average="weighted", zero_division=0)

        # Per-class metrics
        class_ids = sorted(list(id_to_label.keys()))
        p_class, r_class, f1_class, support_class = precision_recall_fscore_support(
            y_true, y_pred, labels=class_ids, average=None, zero_division=0
        )

        per_class_dict = {}
        for cid, p, r, f1, sup in zip(class_ids, p_class, r_class, f1_class, support_class):
            lbl_name = id_to_label.get(cid, str(cid))
            per_class_dict[lbl_name] = {
                "precision": round(float(p), 4),
                "recall": round(float(r), 4),
                "f1": round(float(f1), 4),
                "support": int(sup)
            }

        cm = confusion_matrix(y_true, y_pred, labels=class_ids).tolist()

        return {
            "accuracy": round(acc, 4),
            "macro_precision": round(float(p_macro), 4),
            "macro_recall": round(float(r_macro), 4),
            "macro_f1": round(float(f1_macro), 4),
            "weighted_f1": round(float(f1_weighted), 4),
            "per_class": per_class_dict,
            "confusion_matrix": cm
        }
