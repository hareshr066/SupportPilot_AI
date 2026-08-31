import os
import json
import logging
from typing import List, Dict, Tuple, Optional, Any
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    get_linear_schedule_with_warmup
)

from config import settings
from app.ml.severity_dataset import SeverityExample

logger = logging.getLogger(__name__)


def get_device() -> torch.device:
    """Detects available computing device (CUDA or CPU)."""
    if torch.cuda.is_available():
        device = torch.device("cuda")
        logger.info(f"Using CUDA GPU device: {torch.cuda.get_device_name(0)}")
    else:
        device = torch.device("cpu")
        logger.info("Using CPU device for model training and inference.")
    return device


class SeverityPyTorchDataset(Dataset):
    """PyTorch Dataset wrapper for severity classification examples."""

    def __init__(self, examples: List[SeverityExample], tokenizer, max_length: int = 256):
        self.examples = examples
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        example = self.examples[idx]
        # Format input text ensuring Title is preserved
        text = example.text
        encoding = self.tokenizer(
            text,
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt"
        )
        item = {key: val.squeeze(0) for key, val in encoding.items()}
        item["labels"] = torch.tensor(example.target_id, dtype=torch.long)
        return item


class SeverityTransformerModel:
    """
    DistilBERT Sequence Classifier for Severity/Priority Prediction.
    Supports supervised training, evaluation, saving/loading artifacts, and device configuration.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        num_labels: int = 2,
        label_to_id: Optional[Dict[str, int]] = None,
        id_to_label: Optional[Dict[int, str]] = None,
        max_length: Optional[int] = None,
        device: Optional[torch.device] = None
    ):
        self.model_name = model_name or settings.severity_model_name
        self.num_labels = num_labels
        self.label_to_id = label_to_id or {}
        self.id_to_label = id_to_label or {}
        self.max_length = max_length or settings.severity_max_length
        self.device = device or get_device()

        self.tokenizer = None
        self.model = None

    def initialize_new_model(self):
        """Loads pretrained tokenizer and sequence classification model."""
        logger.info(f"Initializing Transformer model '{self.model_name}' with num_labels={self.num_labels}...")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name,
            num_labels=self.num_labels
        )
        self.model.to(self.device)

    def train_model(
        self,
        train_examples: List[SeverityExample],
        val_examples: List[SeverityExample],
        batch_size: int = 16,
        epochs: int = 3,
        learning_rate: float = 2e-5,
        random_seed: int = 42
    ) -> Dict[str, Any]:
        """
        Executes supervised PyTorch training loop for DistilBERT with linear learning rate schedule.
        """
        torch.manual_seed(random_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(random_seed)

        if not self.tokenizer or not self.model:
            self.initialize_new_model()

        train_dataset = SeverityPyTorchDataset(train_examples, self.tokenizer, self.max_length)
        val_dataset = SeverityPyTorchDataset(val_examples, self.tokenizer, self.max_length)

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

        optimizer = AdamW(self.model.parameters(), lr=learning_rate, weight_decay=0.01)
        total_steps = len(train_loader) * epochs
        scheduler = get_linear_schedule_with_warmup(
            optimizer,
            num_warmup_steps=int(total_steps * 0.1),
            num_training_steps=total_steps
        )

        logger.info(f"Starting DistilBERT training for {epochs} epochs ({total_steps} steps)...")
        self.model.train()

        history = {"train_loss": [], "val_loss": []}

        for epoch in range(epochs):
            total_train_loss = 0.0
            for batch in train_loader:
                optimizer.zero_grad()
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                labels = batch["labels"].to(self.device)

                outputs = self.model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=labels
                )

                loss = outputs.loss
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)

                optimizer.step()
                scheduler.step()

                total_train_loss += loss.item()

            avg_train_loss = total_train_loss / max(1, len(train_loader))
            history["train_loss"].append(avg_train_loss)

            # Validation loss evaluation
            self.model.eval()
            total_val_loss = 0.0
            with torch.no_grad():
                for batch in val_loader:
                    input_ids = batch["input_ids"].to(self.device)
                    attention_mask = batch["attention_mask"].to(self.device)
                    labels = batch["labels"].to(self.device)

                    outputs = self.model(
                        input_ids=input_ids,
                        attention_mask=attention_mask,
                        labels=labels
                    )
                    total_val_loss += outputs.loss.item()

            avg_val_loss = total_val_loss / max(1, len(val_loader))
            history["val_loss"].append(avg_val_loss)

            logger.info(
                f"Epoch {epoch+1}/{epochs} - Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f}"
            )
            self.model.train()

        return history

    def predict_probs(self, texts: List[str]) -> Tuple[List[int], List[float]]:
        """Generates predicted label IDs and softmax confidence scores for input texts."""
        if not self.model or not self.tokenizer:
            raise RuntimeError("Model or tokenizer is not initialized.")

        self.model.eval()
        predicted_ids = []
        confidence_scores = []

        for text in texts:
            inputs = self.tokenizer(
                text,
                truncation=True,
                max_length=self.max_length,
                padding="max_length",
                return_tensors="pt"
            ).to(self.device)

            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=-1).squeeze(0)
                pred_id = int(torch.argmax(probs).item())
                score = float(probs[pred_id].item())

                predicted_ids.append(pred_id)
                confidence_scores.append(score)

        return predicted_ids, confidence_scores

    def save_model_artifacts(self, output_dir: str):
        """Saves model weights, tokenizer, label mapping, and training config to specified directory."""
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Saving severity model artifacts to '{output_dir}'...")

        self.model.save_pretrained(output_dir)
        self.tokenizer.save_pretrained(output_dir)

        # Save label mappings and training config
        mapping_data = {
            "label_to_id": self.label_to_id,
            "id_to_label": {str(k): v for k, v in self.id_to_label.items()},
            "model_name": self.model_name,
            "max_length": self.max_length,
            "num_labels": self.num_labels
        }
        with open(os.path.join(output_dir, "label_mapping.json"), "w", encoding="utf-8") as f:
            json.dump(mapping_data, f, indent=2)

        logger.info(f"Severity model artifacts saved successfully to '{output_dir}'.")

    @classmethod
    def load_model_artifacts(cls, artifact_dir: str, device: Optional[torch.device] = None) -> "SeverityTransformerModel":
        """Loads trained model, tokenizer, and label mappings from artifact directory."""
        mapping_file = os.path.join(artifact_dir, "label_mapping.json")
        if not os.path.exists(mapping_file):
            raise FileNotFoundError(f"Label mapping file not found at '{mapping_file}'.")

        with open(mapping_file, "r", encoding="utf-8") as f:
            mapping_data = json.load(f)

        label_to_id = mapping_data["label_to_id"]
        id_to_label = {int(k): v for k, v in mapping_data["id_to_label"].items()}
        num_labels = mapping_data.get("num_labels", len(label_to_id))
        max_length = mapping_data.get("max_length", 256)

        target_device = device or get_device()

        logger.info(f"Loading severity model from artifact directory '{artifact_dir}'...")
        tokenizer = AutoTokenizer.from_pretrained(artifact_dir)
        model = AutoModelForSequenceClassification.from_pretrained(artifact_dir)
        model.to(target_device)

        instance = cls(
            model_name=mapping_data.get("model_name", settings.severity_model_name),
            num_labels=num_labels,
            label_to_id=label_to_id,
            id_to_label=id_to_label,
            max_length=max_length,
            device=target_device
        )
        instance.tokenizer = tokenizer
        instance.model = model

        return instance
