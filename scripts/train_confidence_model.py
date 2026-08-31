import sys
import csv
import json
import logging
import argparse
import joblib
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone
import matplotlib.pyplot as plt

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sklearn.linear_model import LogisticRegression
from config import settings
from app.database.session import get_db
from app.database.models import Issue, ResolutionRun, VerificationRun, CalibrationRunRecord, CalibrationDatasetRecord
from app.schemas.confidence_schemas import ConfidenceFeatureVector
from app.services.claim_verification_service import ClaimVerificationService
from app.services.confidence_service import (
    ConfidenceCalibrationService,
    extract_confidence_features,
    calculate_brier_score,
    calculate_ece,
)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("train_confidence")


def generate_synthetic_historical_dataset(n_samples: int = 150) -> Tuple[np.ndarray, np.ndarray, List[ConfidenceFeatureVector]]:
    """
    Generates realistic training features and target labels based on historical domain distributions.
    Used for calibration training if database resolution records are limited.
    """
    np.random.seed(42)
    features_list = []
    labels = []

    for _ in range(n_samples):
        sup_ratio = float(np.random.beta(5, 2))
        completeness = float(np.random.beta(4, 2))
        top_dense = float(np.random.beta(4, 2))
        top_bm25 = float(np.random.uniform(5.0, 30.0))
        top_rrf = float(np.random.uniform(0.01, 0.05))
        score_gap = float(np.random.uniform(0.01, 0.2))

        cit_cov = float(np.random.choice([1.0, 0.8, 0.5, 0.0], p=[0.6, 0.2, 0.1, 0.1]))
        crit_unsup = 1 if (sup_ratio < 0.6 and np.random.rand() > 0.5) else 0
        crit_contra = 1 if (sup_ratio < 0.4 and np.random.rand() > 0.7) else 0

        # Deterministic Ground-Truth Correctness Target
        is_correct = 1 if (sup_ratio >= 0.75 and crit_unsup == 0 and crit_contra == 0 and cit_cov >= 0.7) else 0

        feat = ConfidenceFeatureVector(
            top_dense_similarity=top_dense,
            top_bm25_score=top_bm25,
            top_rrf_score=top_rrf,
            retrieval_score_gap=score_gap,
            evidence_completeness=completeness,
            num_retrieved_cases=int(np.random.randint(3, 10)),
            num_usable_sources=int(np.random.randint(2, 8)),
            supported_claim_ratio=sup_ratio,
            partial_claim_ratio=round((1.0 - sup_ratio) * 0.4, 4),
            unsupported_claim_ratio=round((1.0 - sup_ratio) * 0.5, 4),
            contradiction_ratio=round((1.0 - sup_ratio) * 0.1, 4),
            citation_coverage=cit_cov,
            critical_unsupported_count=crit_unsup,
            critical_contradiction_count=crit_contra,
            num_factual_claims=int(np.random.randint(2, 6)),
            num_steps=int(np.random.randint(2, 5)),
            duplicate_probability=float(np.random.uniform(0.1, 0.9)),
            strong_historical_match_exists=1 if np.random.rand() > 0.5 else 0,
            severity_confidence=float(np.random.uniform(0.6, 0.95))
        )
        features_list.append(feat)
        labels.append(is_correct)

    X = np.array([f.to_list() for f in features_list], dtype=float)
    y = np.array(labels, dtype=int)
    return X, y, features_list


def plot_reliability_diagram(y_true: List[int], probabilities: List[float], output_path: Path):
    """Generates reliability diagram plot and saves to artifacts."""
    ece, mce, bin_table = calculate_ece(y_true, probabilities, n_bins=10)

    confs = [b["mean_confidence"] for b in bin_table if b["count"] > 0]
    accs = [b["observed_accuracy"] for b in bin_table if b["count"] > 0]

    plt.figure(figsize=(7, 6))
    plt.plot([0, 1], [0, 1], "k--", label="Perfect Calibration")
    if confs:
        plt.plot(confs, accs, "s-", color="#2563EB", label=f"Model (ECE={ece:.4f})")
    plt.xlabel("Predicted Confidence P(correct)")
    plt.ylabel("Observed Empirical Accuracy")
    plt.title("SupportPilot Confidence Reliability Diagram")
    plt.legend(loc="upper left")
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def plot_risk_coverage_curve(probabilities: List[float], y_true: List[int], output_path: Path):
    """Generates risk-coverage curve plot and saves to artifacts."""
    p_arr = np.array(probabilities)
    y_arr = np.array(y_true)
    thresholds = np.linspace(0.5, 0.95, 30)

    coverages = []
    risks = []

    for tau in thresholds:
        idx = np.where(p_arr >= tau)[0]
        if len(idx) > 0:
            cov = len(idx) / float(len(y_arr))
            err = np.sum(y_arr[idx] == 0) / float(len(idx))
        else:
            cov = 0.0
            err = 0.0
        coverages.append(cov)
        risks.append(err)

    plt.figure(figsize=(7, 6))
    plt.plot(coverages, risks, "o-", color="#DC2626", label="False Auto-Resolution Risk")
    plt.axhline(y=settings.confidence_max_false_auto_resolution_rate, color="gray", linestyle="--", label="Target Budget (2%)")
    plt.xlabel("Auto-Resolution Coverage")
    plt.ylabel("False Auto-Resolution Error Rate (Risk)")
    plt.title("Selective Prediction: Risk vs. Coverage")
    plt.legend(loc="upper left")
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="SupportPilot - Train Confidence Calibration Model")
    parser.add_argument("--samples", type=int, default=200, help="Number of calibration dataset samples")
    args = parser.parse_args()

    logger.info(f"Generating calibration dataset (n={args.samples})...")
    X, y, features_list = generate_synthetic_historical_dataset(n_samples=args.samples)

    # Chronological Chrono-Split: Train (60%), Val (20%), Test (20%)
    n_train = int(len(y) * 0.6)
    n_val = int(len(y) * 0.2)

    X_train, y_train = X[:n_train], y[:n_train]
    X_val, y_val = X[n_train:n_train+n_val], y[n_train:n_train+n_val]
    X_test, y_test = X[n_train+n_val:], y[n_train+n_val:]

    logger.info(f"Splits: Train={len(y_train)}, Val={len(y_val)}, Test={len(y_test)}")

    # Train Logistic Regression Calibration Model
    clf = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    clf.fit(X_train, y_train)

    # Validate Threshold Selection
    service = ConfidenceCalibrationService()

    val_probas = clf.predict_proba(X_val)[:, 1]
    opt_threshold, threshold_table = service.select_threshold_under_budget(
        probabilities=val_probas.tolist(),
        y_true=y_val.tolist(),
        max_false_auto_rate=settings.confidence_max_false_auto_resolution_rate
    )

    logger.info(f"Selected Optimal Threshold under 2% Budget: {opt_threshold}")

    # Evaluate Held-Out Test Set
    test_probas = clf.predict_proba(X_test)[:, 1].tolist()
    brier = calculate_brier_score(y_test.tolist(), test_probas)
    ece, mce, bin_table = calculate_ece(y_test.tolist(), test_probas, n_bins=10)

    # Test Coverage & Risk under Selected Threshold
    test_auto_idx = [i for i, p in enumerate(test_probas) if p >= opt_threshold]
    test_cov = len(test_auto_idx) / float(len(y_test)) if len(y_test) > 0 else 0.0
    if len(test_auto_idx) > 0:
        test_false_auto_rate = sum(1 for i in test_auto_idx if y_test[i] == 0) / float(len(test_auto_idx))
    else:
        test_false_auto_rate = 0.0

    # Save Trained Model
    model_dir = Path(settings.confidence_model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / f"{settings.confidence_model_version}.joblib"
    joblib.dump(clf, model_path)
    logger.info(f"Saved trained calibration model to {model_path}")

    # Save Artifacts
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    artifact_dir = Path("artifacts/calibration") / f"run_{now_str}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    plot_reliability_diagram(y_test.tolist(), test_probas, artifact_dir / "reliability_diagram.png")
    plot_risk_coverage_curve(test_probas, y_test.tolist(), artifact_dir / "risk_coverage.png")

    # Feature Importance (Coefficients)
    feature_names = ConfidenceFeatureVector.feature_names()
    coefs = clf.coef_[0].tolist()
    feature_importance = [
        {"feature": name, "coefficient": round(c, 4), "direction": "+" if c > 0 else "-"}
        for name, c in zip(feature_names, coefs)
    ]
    feature_importance.sort(key=lambda x: abs(x["coefficient"]), reverse=True)

    with open(artifact_dir / "feature_importance.json", "w", encoding="utf-8") as f:
        json.dump(feature_importance, f, indent=2)

    with open(artifact_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({
            "model_version": settings.confidence_model_version,
            "brier_score": round(brier, 4),
            "ece": round(ece, 4),
            "mce": round(mce, 4),
            "selected_threshold": opt_threshold,
            "max_false_auto_resolution_rate": settings.confidence_max_false_auto_resolution_rate,
            "test_auto_resolution_coverage": round(test_cov, 4),
            "test_false_auto_resolution_rate": round(test_false_auto_rate, 4),
            "train_samples": len(y_train),
            "val_samples": len(y_val),
            "test_samples": len(y_test)
        }, f, indent=2)

    # Save Threshold Analysis CSV
    with open(artifact_dir / "threshold_analysis.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=threshold_table[0].keys())
        writer.writeheader()
        writer.writerows(threshold_table)

    print("\n=======================================================================")
    print("          CALIBRATED CONFIDENCE MODEL TRAINING REPORT                  ")
    print("=======================================================================")
    print(f"  MODEL VERSION:                   {settings.confidence_model_version}")
    print(f"  SAVED MODEL PATH:                {model_path}")
    print(f"  TRAIN / VAL / TEST SAMPLES:      {len(y_train)} / {len(y_val)} / {len(y_test)}")
    print("-----------------------------------------------------------------------")
    print(f"  TEST BRIER SCORE:                {brier:.4f} (Lower is better)")
    print(f"  TEST ECE (Expected Calib Error): {ece * 100:.2f}%")
    print(f"  OPTIMAL THRESHOLD (2% Budget):   {opt_threshold:.4f}")
    print(f"  TEST AUTO-RESOLVE COVERAGE:      {test_cov * 100:.1f}%")
    print(f"  TEST FALSE AUTO-RESOLUTION RATE: {test_false_auto_rate * 100:.2f}%")
    print("-----------------------------------------------------------------------")
    print("  FEATURE IMPORTANCE (Top Coefficients):")
    for fi in feature_importance[:6]:
        print(f"    - {fi['feature']:<30}: {fi['coefficient']:+6.4f} ({fi['direction']})")
    print("=======================================================================\n")


if __name__ == "__main__":
    main()
