from dataclasses import dataclass, field
from typing import List

@dataclass
class EvaluationConfig:
    dataset_version: str = "github_dataset_v1"
    code_version: str = "v1.0.0"
    feature_version: str = "v1.0"
    train_ratio: float = 0.60
    val_ratio: float = 0.20
    test_ratio: float = 0.20
    random_seed: int = 42
    duplicate_threshold_grid: List[float] = field(default_factory=lambda: [0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
    retrieval_k_values: List[int] = field(default_factory=lambda: [1, 3, 5, 10, 20])
    confidence_thresholds: List[float] = field(default_factory=lambda: [0.70, 0.75, 0.80, 0.85, 0.90, 0.95])
    false_positive_budgets: List[float] = field(default_factory=lambda: [0.01, 0.02, 0.05])
    min_sample_threshold: int = 3
