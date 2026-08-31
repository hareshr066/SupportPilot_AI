import os
import sys
import logging
import argparse
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.session import get_db
from app.database.models import Repository
from app.ml.severity_dataset import prepare_severity_dataset
from app.ml.severity_baseline import SeverityBaselineModel
from app.ml.severity_model import SeverityTransformerModel
from app.services.severity_evaluator import evaluate_severity_predictions, save_evaluation_report

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("train_severity_model")


def main() -> None:
    parser = argparse.ArgumentParser(description="SupportPilot - Severity Model Training & Evaluation")
    parser.add_argument("--owner", type=str, default="microsoft", help="Repository owner")
    parser.add_argument("--repo", type=str, default="vscode", help="Repository name")
    parser.add_argument("--severity-labels", type=str, nargs="+", default=["priority:low", "priority:medium", "priority:high", "priority:critical"], help="Valid severity label names")
    parser.add_argument("--output-dir", type=str, default=settings.severity_model_path, help="Directory to save model artifacts")
    parser.add_argument("--epochs", type=int, default=settings.severity_epochs, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=settings.severity_batch_size, help="Training batch size")
    parser.add_argument("--lr", type=float, default=settings.severity_learning_rate, help="Learning rate")
    args = parser.parse_args()

    repo_full_name = f"{args.owner}/{args.repo}"

    with get_db() as session:
        from sqlalchemy import select
        repository = session.scalar(
            select(Repository).where(Repository.owner == args.owner, Repository.name == args.repo)
        )
        if not repository:
            logger.error(f"Repository '{repo_full_name}' not found in PostgreSQL database.")
            sys.exit(1)
        repo_id = repository.id

    logger.info(f"Preparing severity dataset for repository '{repo_full_name}'...")
    split = prepare_severity_dataset(
        repository_id=repo_id,
        valid_severity_labels=args.severity_labels
    )

    logger.info("==========================================")
    logger.info("       Severity Dataset Summary           ")
    logger.info("==========================================")
    logger.info(f"  Repository:                   {repo_full_name}")
    logger.info(f"  Valid Severity Labels:        {args.severity_labels}")
    logger.info(f"  Train Set Count:              {len(split.train_examples)}")
    logger.info(f"  Validation Set Count:         {len(split.val_examples)}")
    logger.info(f"  Test Set Count:               {len(split.test_examples)}")
    logger.info(f"  Unlabeled Excluded:           {split.unlabeled_excluded_count}")
    logger.info(f"  Ambiguous Excluded:           {split.ambiguous_excluded_count}")
    logger.info("==========================================")

    if len(split.train_examples) == 0:
        logger.warning(
            f"[DATASET LIMITATION] Repository '{repo_full_name}' has 0 labeled severity examples in PostgreSQL. "
            "Supervised model training cannot be performed on this repository sample."
        )
        sys.exit(0)

    # ---------------------------------------------------------
    # Baseline Model Evaluation (TF-IDF + Logistic Regression)
    # ---------------------------------------------------------
    logger.info("Training TF-IDF + Logistic Regression Baseline Model...")
    baseline = SeverityBaselineModel()
    baseline.train(split.train_examples)

    baseline_report = baseline.evaluate(split.test_examples, split.id_to_label)
    logger.info(f"Baseline Test Accuracy: {baseline_report['accuracy']} | Macro F1: {baseline_report['macro_f1']} | Weighted F1: {baseline_report['weighted_f1']}")

    # ---------------------------------------------------------
    # Supervised DistilBERT Transformer Training & Evaluation
    # ---------------------------------------------------------
    logger.info("Initializing DistilBERT Transformer Model...")
    model = SeverityTransformerModel(
        model_name=settings.severity_model_name,
        num_labels=len(split.label_to_id),
        label_to_id=split.label_to_id,
        id_to_label=split.id_to_label,
        max_length=settings.severity_max_length
    )
    model.initialize_new_model()

    model.train_model(
        train_examples=split.train_examples,
        val_examples=split.val_examples,
        batch_size=args.batch_size,
        epochs=args.epochs,
        learning_rate=args.lr,
        random_seed=settings.severity_random_seed
    )

    # Evaluate Transformer model on test set
    test_texts = [ex.text for ex in split.test_examples]
    test_true = [ex.target_id for ex in split.test_examples]

    test_pred, test_scores = model.predict_probs(test_texts)

    eval_report = evaluate_severity_predictions(
        y_true=test_true,
        y_pred=test_pred,
        y_scores=test_scores,
        examples=split.test_examples,
        id_to_label=split.id_to_label
    )

    logger.info("==========================================")
    logger.info("  DistilBERT Test Evaluation Summary      ")
    logger.info("==========================================")
    logger.info(f"  Test Accuracy:        {eval_report['accuracy']}")
    logger.info(f"  Macro Precision:      {eval_report['macro_precision']}")
    logger.info(f"  Macro Recall:         {eval_report['macro_recall']}")
    logger.info(f"  Macro F1:             {eval_report['macro_f1']}")
    logger.info(f"  Weighted F1:          {eval_report['weighted_f1']}")
    logger.info(f"  Baseline Macro F1:    {baseline_report['macro_f1']}")
    logger.info("==========================================")

    # Save model artifacts and evaluation report
    model.save_model_artifacts(args.output_dir)
    save_evaluation_report(eval_report, os.path.join(args.output_dir, "evaluation_report.json"))


if __name__ == "__main__":
    main()
