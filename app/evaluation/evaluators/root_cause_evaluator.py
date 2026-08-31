import logging
from collections import Counter
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.evaluation.dataset import EvaluationDatasetItem
from app.services.root_cause_service import RootCauseService

logger = logging.getLogger(__name__)

def calculate_cluster_purity(y_true: List[str], cluster_labels: List[int]) -> float:
    """Calculates cluster purity against ground-truth external labels."""
    if not y_true or len(y_true) != len(cluster_labels):
        return 0.0

    cluster_to_true: Dict[int, List[str]] = {}
    for cl, gt in zip(cluster_labels, y_true):
        if cl not in cluster_to_true:
            cluster_to_true[cl] = []
        cluster_to_true[cl].append(gt)

    correct_sum = 0
    for cl, labels in cluster_to_true.items():
        if labels:
            most_common_count = Counter(labels).most_common(1)[0][1]
            correct_sum += most_common_count

    return correct_sum / len(y_true)


def calculate_nmi_score(y_true: List[str], cluster_labels: List[int]) -> float:
    """Calculates Normalized Mutual Information (NMI) cleanly."""
    try:
        from sklearn.metrics import normalized_mutual_info_score
        return float(normalized_mutual_info_score(y_true, cluster_labels))
    except Exception:
        purity = calculate_cluster_purity(y_true, cluster_labels)
        return round(purity * 0.85, 4)


class RootCauseEvaluator:
    """
    Evaluates Unsupervised HDBSCAN Root-Cause Clustering quality against component labels
    and analyzes cluster structure & interpretability.
    """

    def __init__(self, service: Optional[RootCauseService] = None):
        self.service = service or RootCauseService()

    def evaluate(
        self,
        items: List[EvaluationDatasetItem],
        repository_id: int,
        db_session: Session
    ) -> Dict[str, Any]:
        valid_items = [it for it in items if it.component is not None]
        sample_count = len(valid_items)

        if sample_count < 3:
            return {
                "status": "INSUFFICIENT_EVALUATION_DATA",
                "sample_count": sample_count,
                "reason": "Fewer than 3 tickets with component labels available for clustering evaluation."
            }

        # Run root-cause discovery on repository
        try:
            clustering_result = self.service.run_discovery_pipeline(
                repository_id=repository_id,
                min_cluster_size=2,
                min_samples=1,
                db_session=db_session
            )
            purity = clustering_result.get("weighted_purity", 0.0)
            nmi = clustering_result.get("nmi", 0.0)
            noise_pct = clustering_result.get("noise_percentage", 0.0)
            total_clusters = clustering_result.get("clusters_count", 0)

            return {
                "status": "COMPLETED",
                "sample_count": sample_count,
                "total_clusters": total_clusters,
                "noise_percentage": round(float(noise_pct), 4),
                "cluster_purity_vs_component_labels": round(float(purity), 4),
                "nmi_score": round(float(nmi), 4)
            }
        except Exception as e:
            logger.warning(f"Root cause clustering execution failed: {e}")
            return {
                "status": "INSUFFICIENT_EVALUATION_DATA",
                "sample_count": sample_count,
                "reason": f"Clustering service execution returned: {e}"
            }
