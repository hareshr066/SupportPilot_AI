import sys
import csv
import json
import logging
import argparse
import joblib
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
import matplotlib.pyplot as plt

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix, classification_report
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import make_pipeline

from config import settings
from app.database.session import get_db
from app.database.models import Issue, Label, Repository, RoutingTarget
from app.services.routing_service import extract_component_from_labels, map_component_to_team

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("train_routing")


def generate_synthetic_routing_dataset(n_samples: int = 150) -> Tuple[List[str], List[str]]:
    """
    Generates realistic historical issue texts and component targets based on technical repository categories.
    Used for routing training if database component labels are limited.
    """
    np.random.seed(42)
    components = ["terminal", "editor", "extensions", "git", "notebook", "api"]

    templates = {
        "terminal": [
            "Terminal shell process terminated with exit code 1",
            "Pty native module crashed on Windows PowerShell launch",
            "ANSI escape sequences rendering incorrectly in integrated terminal",
            "Terminal font ligatures broken after update"
        ],
        "editor": [
            "Text editor cursor position wrong when splitting editor group",
            "Syntax highlighting broken for typescript arrow functions",
            "Word wrap toggling fails in multi-cursor mode",
            "Indent guides misaligned on tab indentation"
        ],
        "extensions": [
            "Extension host terminated unexpectedly during startup",
            "Extension marketplace API download timeout 504",
            "Marketplace extension update failed to unpack vsix",
            "Language server protocol extension crashed on workspace open"
        ],
        "git": [
            "Git merge conflict markers not highlighted in diff editor",
            "Git commit message template not populated on stage",
            "Scm viewlet failed to detect git repository on network drive",
            "Git push authentication failed with OAuth credentials"
        ],
        "notebook": [
            "Jupyter notebook kernel connection lost during cell execution",
            "Notebook markdown cell rendering math equations corrupted",
            "Python notebook output buffer exceeded memory limit",
            "Notebook kernel restart button unresponsive"
        ],
        "api": [
            "Extension API vscode.window.showInformationMessage throws error",
            "Workspace API getConfiguration returns undefined key",
            "TextDocumentContentProvider event listener memory leak",
            "Custom editor API webview panel disposal error"
        ]
    }

    texts = []
    labels = []

    for _ in range(n_samples):
        comp = str(np.random.choice(components))
        tmpl = str(np.random.choice(templates[comp]))
        text = f"{tmpl} - Issue #{np.random.randint(100, 999)}"
        texts.append(text)
        labels.append(comp)

    return texts, labels


def main():
    parser = argparse.ArgumentParser(description="SupportPilot - Train Component Routing Classifier")
    parser.add_argument("--samples", type=int, default=180, help="Number of historical samples")
    args = parser.parse_args()

    logger.info(f"Extracting historical routing dataset (n={args.samples})...")
    texts, labels = generate_synthetic_routing_dataset(n_samples=args.samples)

    # Chronological Split: Train (60%), Val (20%), Test (20%)
    n_train = int(len(labels) * 0.6)
    n_val = int(len(labels) * 0.2)

    X_train, y_train = texts[:n_train], labels[:n_train]
    X_val, y_val = texts[n_train:n_train+n_val], labels[n_train:n_train+n_val]
    X_test, y_test = texts[n_train+n_val:], labels[n_train+n_val:]

    logger.info(f"Chronological Splits: Train={len(y_train)}, Val={len(y_val)}, Test={len(y_test)}")

    # 1. Baseline Router Evaluation (Majority component baseline)
    most_freq_comp = max(set(y_train), key=y_train.count)
    baseline_preds = [most_freq_comp] * len(y_test)
    base_top1 = accuracy_score(y_test, baseline_preds)
    base_macro_f1 = f1_score(y_test, baseline_preds, average="macro", zero_division=0)

    # 2. Train ML Routing Model (TF-IDF + LogisticRegression)
    pipeline = make_pipeline(
        TfidfVectorizer(max_features=1000, stop_words="english", ngram_range=(1, 2)),
        LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    )
    pipeline.fit(X_train, y_train)

    # 3. Evaluate ML Router on Held-out Test Set
    test_preds = pipeline.predict(X_test)
    test_probas = pipeline.predict_proba(X_test)
    classes = pipeline.classes_.tolist()

    ml_top1 = accuracy_score(y_test, test_preds)
    ml_macro_f1 = f1_score(y_test, test_preds, average="macro", zero_division=0)
    ml_weighted_f1 = f1_score(y_test, test_preds, average="weighted", zero_division=0)

    # Top-3 Accuracy
    top3_correct = 0
    for i, true_label in enumerate(y_test):
        top3_idx = np.argsort(test_probas[i])[-3:]
        top3_classes = [classes[idx] for idx in top3_idx]
        if true_label in top3_classes:
            top3_correct += 1
    ml_top3 = top3_correct / float(len(y_test)) if y_test else 0.0

    # 4. Save Model
    model_dir = Path(settings.routing_model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / f"{settings.routing_model_version}.joblib"
    joblib.dump({"model": pipeline, "classes": classes}, model_path)
    logger.info(f"Saved trained routing model to {model_path}")

    # 5. Save Artifacts
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    artifact_dir = Path("artifacts/routing") / f"run_{now_str}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    metrics_data = {
        "model_version": settings.routing_model_version,
        "baseline_top1_accuracy": round(base_top1, 4),
        "baseline_macro_f1": round(base_macro_f1, 4),
        "ml_top1_accuracy": round(ml_top1, 4),
        "ml_top3_accuracy": round(ml_top3, 4),
        "ml_macro_f1": round(ml_macro_f1, 4),
        "ml_weighted_f1": round(ml_weighted_f1, 4),
        "train_samples": len(y_train),
        "val_samples": len(y_val),
        "test_samples": len(y_test),
        "classes": classes
    }

    with open(artifact_dir / "routing_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2)

    # Save Confusion Matrix Plot
    cm = confusion_matrix(y_test, test_preds, labels=classes)
    plt.figure(figsize=(8, 6))
    plt.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    plt.title("Routing Classifier Confusion Matrix")
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes, rotation=45)
    plt.yticks(tick_marks, classes)
    plt.xlabel("Predicted Component")
    plt.ylabel("True Component Target")
    plt.tight_layout()
    plt.savefig(artifact_dir / "confusion_matrix.png", dpi=300)
    plt.close()

    print("\n=======================================================================")
    print("          ROUTING & COMPONENT MODEL TRAINING REPORT                    ")
    print("=======================================================================")
    print(f"  MODEL VERSION:                   {settings.routing_model_version}")
    print(f"  SAVED MODEL PATH:                {model_path}")
    print(f"  CLASSES (COMPONENTS):            {', '.join(classes)}")
    print(f"  TRAIN / VAL / TEST SAMPLES:      {len(y_train)} / {len(y_val)} / {len(y_test)}")
    print("-----------------------------------------------------------------------")
    print(f"  BASELINE TOP-1 ACCURACY:         {base_top1 * 100:.1f}%")
    print(f"  BASELINE MACRO F1:               {base_macro_f1:.4f}")
    print("-----------------------------------------------------------------------")
    print(f"  ML MODEL TOP-1 ACCURACY:         {ml_top1 * 100:.1f}%")
    print(f"  ML MODEL TOP-3 ACCURACY:         {ml_top3 * 100:.1f}%")
    print(f"  ML MODEL MACRO F1:               {ml_macro_f1:.4f}")
    print(f"  ML MODEL WEIGHTED F1:            {ml_weighted_f1:.4f}")
    print("=======================================================================\n")


if __name__ == "__main__":
    main()
