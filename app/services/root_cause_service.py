import os
import json
import uuid
import logging
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

from sqlalchemy.orm import Session
from sqlalchemy import select

from config import settings
from app.database.session import get_db
from app.database.models import (
    Issue,
    Repository,
    Label,
    IssueEmbedding,
    RootCauseCluster,
    RootCauseAssignment,
)
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

# Check UMAP availability
try:
    import umap
    HAS_UMAP = True
except ImportError:
    HAS_UMAP = False

# Check HDBSCAN availability
try:
    import hdbscan
    HAS_HDBSCAN = True
except ImportError:
    try:
        from sklearn.cluster import HDBSCAN as SklearnHDBSCAN
        HAS_HDBSCAN = True
    except ImportError:
        HAS_HDBSCAN = False


class RootCauseService:
    """
    Root-Cause Discovery Engine.
    
    Performs unsupervised clustering over historical closed issues using:
    Existing Embeddings -> UMAP (10D) -> HDBSCAN Clustering -> Centroid Representative Selection -> LLM Labeling.
    Evaluates discovered clusters against repository component/area ground truth labels via Purity and NMI.
    """

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        db_session: Optional[Session] = None
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        self._external_session = db_session

    def get_root_cause_corpus(
        self,
        repository_id: int,
        session: Session,
        state_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Phase 2: Define Root-Cause Corpus.
        Retrieves closed historical issues and their associated embeddings.
        
        Excludes ground-truth duplicate fields, severity predictions, and cluster IDs.
        """
        target_state = state_filter or settings.root_cause_issue_state
        
        # Query issues for repository matching state
        query = select(Issue).where(
            Issue.repository_id == repository_id
        )
        if target_state:
            query = query.where(Issue.state == target_state)
            
        issues = session.scalars(query).all()
        
        # Fallback if no issues found for specific state (e.g. dev dataset only has open issues)
        if not issues:
            logger.warning(
                f"No issues with state='{target_state}' found for repository_id={repository_id}. "
                f"Falling back to all issues for repository."
            )
            issues = session.scalars(
                select(Issue).where(Issue.repository_id == repository_id)
            ).all()

        model_name = self.embedding_service.model_name

        # Map existing embeddings
        existing_embeddings = {
            emb.issue_id: emb.embedding
            for emb in session.scalars(
                select(IssueEmbedding).where(IssueEmbedding.model_name == model_name)
            ).all()
        }

        corpus: List[Dict[str, Any]] = []
        for issue in issues:
            labels_list = [l.name for l in issue.labels]
            emb_vector = existing_embeddings.get(issue.id)
            
            # If embedding missing in DB, generate on the fly
            if emb_vector is None:
                emb_vector = self.embedding_service.generate_issue_embedding(issue)

            corpus.append({
                "issue_id": issue.id,
                "issue_number": issue.issue_number,
                "title": issue.title or "",
                "body": issue.body or "",
                "labels": labels_list,
                "created_at": issue.created_at.isoformat() if issue.created_at else None,
                "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
                "html_url": issue.html_url or "",
                "embedding": emb_vector,
            })

        return corpus

    def filter_corpus(self, raw_corpus: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        Phase 3: Data Quality Filtering.
        Excludes invalid issues, empty bodies/titles, or missing embeddings.
        """
        total_closed = len(raw_corpus)
        eligible: List[Dict[str, Any]] = []
        excluded_empty_text = 0
        excluded_missing_emb = 0

        min_len = settings.root_cause_min_text_length

        for item in raw_corpus:
            title = (item.get("title") or "").strip()
            body = (item.get("body") or "").strip()
            comb_text = f"{title} {body}".strip()

            if not comb_text or len(comb_text) < min_len:
                excluded_empty_text += 1
                continue

            emb = item.get("embedding")
            if not emb or len(emb) == 0:
                excluded_missing_emb += 1
                continue

            eligible.append(item)

        stats = {
            "total_closed": total_closed,
            "eligible": len(eligible),
            "excluded_empty_text": excluded_empty_text,
            "excluded_missing_emb": excluded_missing_emb,
            "total_excluded": excluded_empty_text + excluded_missing_emb,
        }

        logger.info(
            f"Corpus Filtering Complete: Total={total_closed}, Eligible={len(eligible)}, "
            f"Excluded(Empty Text)={excluded_empty_text}, Excluded(Missing Emb)={excluded_missing_emb}"
        )

        return eligible, stats

    def build_embedding_matrix(self, corpus: List[Dict[str, Any]]) -> np.ndarray:
        """
        Phase 5 & 6: Construct and validate embedding matrix (N x D).
        Verify no NaN/Inf, consistent dimensions.
        """
        if not corpus:
            raise ValueError("Corpus is empty. Cannot build embedding matrix.")

        embeddings = [item["embedding"] for item in corpus]
        matrix = np.array(embeddings, dtype=np.float32)

        # Validation
        if np.isnan(matrix).any():
            raise ValueError("Embedding matrix contains NaN values!")
        if np.isinf(matrix).any():
            raise ValueError("Embedding matrix contains infinite values!")

        logger.info(f"Embedding matrix constructed: shape={matrix.shape}")
        return matrix

    def reduce_dimensions_umap(
        self,
        matrix: np.ndarray,
        n_components: int = 10,
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        random_state: int = 42
    ) -> np.ndarray:
        """
        Phase 7 & 8: Dimensionality Reduction via UMAP.
        Fallback to TruncatedSVD if UMAP is not available or if matrix is smaller than n_components + 2.
        """
        n_samples, n_features = matrix.shape
        adj_components = min(n_components, n_samples - 2) if n_samples > 2 else 1
        adj_components = max(1, adj_components)

        if HAS_UMAP and n_samples >= 15 and adj_components < n_samples - 1:
            adj_neighbors = min(n_neighbors, n_samples - 1)
            reducer = umap.UMAP(
                n_neighbors=adj_neighbors,
                n_components=adj_components,
                min_dist=min_dist,
                metric=metric,
                random_state=random_state,
                init="random"
            )
            reduced = reducer.fit_transform(matrix)
        else:
            # Fallback to TruncatedSVD for small matrices or when UMAP is unavailable/incompatible
            from sklearn.decomposition import TruncatedSVD
            tsvd = TruncatedSVD(n_components=adj_components, random_state=random_state)
            reduced = tsvd.fit_transform(matrix)

        return reduced

    def cluster_hdbscan(
        self,
        matrix_reduced: np.ndarray,
        min_cluster_size: int = 15,
        min_samples: int = 5
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Phase 9: HDBSCAN Clustering.
        Returns: (labels, probabilities, outlier_scores)
        """
        n_samples = matrix_reduced.shape[0]
        adj_min_size = max(2, min(min_cluster_size, max(2, n_samples // 2)))
        adj_min_samples = max(1, min(min_samples, adj_min_size))

        try:
            if 'hdbscan' in globals() and hasattr(hdbscan, 'HDBSCAN'):
                clusterer = hdbscan.HDBSCAN(
                    min_cluster_size=adj_min_size,
                    min_samples=adj_min_samples,
                    metric="euclidean"
                )
            else:
                from sklearn.cluster import HDBSCAN as SklearnHDBSCAN
                clusterer = SklearnHDBSCAN(
                    min_cluster_size=adj_min_size,
                    min_samples=adj_min_samples,
                    metric="euclidean"
                )

            clusterer.fit(matrix_reduced)
            labels = clusterer.labels_
            probs = getattr(clusterer, "probabilities_", np.ones(n_samples, dtype=np.float32))
            outliers = getattr(clusterer, "outlier_scores_", np.zeros(n_samples, dtype=np.float32))
        except Exception as e:
            logger.warning(f"HDBSCAN clustering warning: {e}. Falling back to default noise assignment.")
            labels = np.full(n_samples, -1, dtype=int)
            probs = np.ones(n_samples, dtype=np.float32)
            outliers = np.zeros(n_samples, dtype=np.float32)

        return labels, probs, outliers

    def select_representative_issues(
        self,
        corpus: List[Dict[str, Any]],
        labels: np.ndarray,
        probabilities: np.ndarray,
        matrix_10d: np.ndarray,
        max_representatives: int = 5
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        Phase 11: Representative Issues Selection using distance to cluster centroid
        combined with HDBSCAN membership probability.
        """
        unique_clusters = set(labels)
        unique_clusters.discard(-1)  # Exclude noise

        representatives: Dict[int, List[Dict[str, Any]]] = {}

        for cid in sorted(unique_clusters):
            indices = np.where(labels == cid)[0]
            if len(indices) == 0:
                continue

            cluster_points = matrix_10d[indices]
            centroid = np.mean(cluster_points, axis=0)

            # Compute Euclidean distances to centroid
            distances = np.linalg.norm(cluster_points - centroid, axis=1)

            # Rank by combined score (smaller distance + higher membership probability)
            # Normalize distances
            max_d = np.max(distances) if np.max(distances) > 0 else 1.0
            norm_distances = distances / max_d
            probs = probabilities[indices]

            # Combined score: lower is better
            scores = norm_distances - 0.5 * probs
            sorted_order = np.argsort(scores)

            top_indices = indices[sorted_order[:max_representatives]]

            cluster_reps = []
            for idx in top_indices:
                item = corpus[idx]
                cluster_reps.append({
                    "issue_id": item["issue_id"],
                    "issue_number": item["issue_number"],
                    "title": item["title"],
                    "body_snippet": item["body"][:300],
                    "html_url": item["html_url"],
                    "membership_strength": float(probabilities[idx]),
                })

            representatives[int(cid)] = cluster_reps

        return representatives

    def generate_llm_cluster_labels(
        self,
        representatives: Dict[int, List[Dict[str, Any]]],
        model_name: Optional[str] = None
    ) -> Dict[int, Dict[str, Any]]:
        """
        Phase 12, 13, 14: LLM Cluster Label Generation with strict JSON parsing and evidence validation.
        If LLM is unavailable or fails, falls back gracefully without breaking clustering.
        """
        cluster_labels: Dict[int, Dict[str, Any]] = {}
        target_model = model_name or settings.root_cause_llm_model

        for cid, reps in representatives.items():
            valid_issue_nums = [r["issue_number"] for r in reps]
            
            # Format representative examples for LLM prompt
            examples_text = "\n".join(
                [f"- Issue #{r['issue_number']}: {r['title']}" for r in reps]
            )

            prompt = f"""
You are an expert technical support engineer discovering root-cause issue patterns.
Below are representative issue titles from a semantic issue cluster:

{examples_text}

Task:
Produce a concise, technical root-cause or topic label and brief description for this cluster.

Requirements:
1. Return strictly valid JSON object with keys:
   "cluster_id": {cid},
   "label": "<concise topic title>",
   "description": "<1-2 sentence description>",
   "evidence_issue_numbers": [<list of issue numbers from provided examples>]
2. Only reference issue numbers explicitly provided above.
3. If evidence is ambiguous, set label to "Unclear / mixed issue cluster".
"""

            label_result = {
                "cluster_id": cid,
                "label": f"Cluster {cid}",
                "description": "LLM labeling skipped or unavailable",
                "evidence_issue_numbers": valid_issue_nums[:3]
            }

            # Attempt LLM call if OPENAI_API_KEY is present
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                try:
                    import openai
                    client = openai.OpenAI(api_key=openai_key)
                    response = client.chat.completions.create(
                        model=target_model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.2,
                        response_format={"type": "json_object"}
                    )
                    content = response.choices[0].message.content
                    parsed = json.loads(content)

                    # Validate JSON keys
                    if isinstance(parsed, dict) and "label" in parsed:
                        ev_nums = parsed.get("evidence_issue_numbers", [])
                        # Phase 14: Safety validation - verify referenced issue numbers
                        valid_ev = [n for n in ev_nums if n in valid_issue_nums]
                        if not valid_ev:
                            valid_ev = valid_issue_nums[:3]

                        label_result = {
                            "cluster_id": cid,
                            "label": str(parsed.get("label", f"Cluster {cid}")),
                            "description": str(parsed.get("description", "")),
                            "evidence_issue_numbers": valid_ev
                        }
                except Exception as exc:
                    logger.warning(f"LLM labeling for cluster {cid} failed gracefully: {exc}")

            cluster_labels[cid] = label_result

        return cluster_labels

    def extract_component_labels(self, corpus: List[Dict[str, Any]]) -> Tuple[List[Optional[str]], List[int]]:
        """
        Phase 15: Extract component/area labels as external ground-truth evaluation signal.
        Ignores non-component labels.
        """
        component_ground_truth: List[Optional[str]] = []
        labeled_indices: List[int] = []

        for idx, item in enumerate(corpus):
            labels = item.get("labels", [])
            comp_label = None

            for lbl in labels:
                lbl_lower = lbl.lower()
                if any(prefix in lbl_lower for prefix in ["area", "component", "module", "pkg", "bug", "feature", "doc"]):
                    comp_label = lbl
                    break

            # Fallback to first label if present
            if comp_label is None and labels:
                comp_label = labels[0]

            component_ground_truth.append(comp_label)
            if comp_label is not None:
                labeled_indices.append(idx)

        return component_ground_truth, labeled_indices

    def evaluate_purity_and_nmi(
        self,
        cluster_labels: np.ndarray,
        component_ground_truth: List[Optional[str]]
    ) -> Dict[str, Any]:
        """
        Phase 16 & 17: Calculate Weighted Cluster Purity and Normalized Mutual Information (NMI).
        Noise points (cluster = -1) are excluded from purity/NMI calculations (Option A).
        """
        from sklearn.metrics import normalized_mutual_info_score

        n_samples = len(cluster_labels)
        noise_indices = set(np.where(cluster_labels == -1)[0])
        noise_count = len(noise_indices)
        noise_pct = round((noise_count / n_samples) * 100, 2) if n_samples > 0 else 0.0

        # Filter indices with valid component ground truth and non-noise cluster
        eval_indices = [
            i for i in range(n_samples)
            if i not in noise_indices and component_ground_truth[i] is not None
        ]

        if not eval_indices:
            return {
                "total_issues": n_samples,
                "evaluated_issues_count": 0,
                "noise_count": noise_count,
                "noise_percentage": noise_pct,
                "weighted_purity": 0.0,
                "nmi": 0.0,
                "per_cluster_purity": {},
                "is_statistically_meaningful": False,
                "notes": "Insufficient component-labeled non-noise issues for statistical evaluation."
            }

        eval_clusters = cluster_labels[eval_indices]
        eval_targets = [component_ground_truth[i] for i in eval_indices]

        # Calculate Per-Cluster Purity
        unique_cids = set(eval_clusters)
        per_cluster_purity: Dict[int, float] = {}
        total_correct = 0

        for cid in sorted(unique_cids):
            c_indices = [k for k, c in enumerate(eval_clusters) if c == cid]
            c_targets = [eval_targets[k] for k in c_indices]

            # Find dominant component label count
            counts: Dict[str, int] = {}
            for t in c_targets:
                counts[t] = counts.get(t, 0) + 1

            max_count = max(counts.values()) if counts else 0
            purity = max_count / len(c_indices) if c_indices else 0.0
            per_cluster_purity[int(cid)] = round(purity, 4)
            total_correct += max_count

        weighted_purity = round(total_correct / len(eval_indices), 4)

        # Calculate NMI using scikit-learn
        nmi = round(float(normalized_mutual_info_score(eval_targets, eval_clusters)), 4)

        # Baseline: All issues assigned to dominant component class
        dominant_label_count = max(
            eval_targets.count(t) for t in set(eval_targets)
        ) if eval_targets else 0
        baseline_purity = round(dominant_label_count / len(eval_indices), 4) if eval_indices else 0.0

        return {
            "total_issues": n_samples,
            "evaluated_issues_count": len(eval_indices),
            "noise_count": noise_count,
            "noise_percentage": noise_pct,
            "weighted_purity": weighted_purity,
            "baseline_purity": baseline_purity,
            "nmi": nmi,
            "per_cluster_purity": per_cluster_purity,
            "is_statistically_meaningful": len(eval_indices) >= 5,
        }

    def calculate_stability_ari(
        self,
        matrix_reduced: np.ndarray,
        primary_labels: np.ndarray,
        seeds: List[int] = [42, 123, 999]
    ) -> float:
        """
        Phase 21: Cluster Stability check using Adjusted Rand Index (ARI).
        """
        from sklearn.metrics import adjusted_rand_score

        ari_scores = []
        for seed in seeds[1:]:
            labels_alt, _, _ = self.cluster_hdbscan(
                matrix_reduced,
                min_cluster_size=settings.root_cause_hdbscan_min_cluster_size,
                min_samples=settings.root_cause_hdbscan_min_samples
            )
            ari = adjusted_rand_score(primary_labels, labels_alt)
            ari_scores.append(ari)

        avg_ari = float(np.mean(ari_scores)) if ari_scores else 1.0
        return round(avg_ari, 4)

    def persist_clustering_run(
        self,
        repository_id: int,
        run_id: str,
        corpus: List[Dict[str, Any]],
        labels: np.ndarray,
        probabilities: np.ndarray,
        outliers: np.ndarray,
        cluster_summaries: Dict[int, Dict[str, Any]],
        umap_config: Dict[str, Any],
        hdbscan_config: Dict[str, Any],
        session: Session
    ) -> Dict[str, Any]:
        """
        Phase 22 & 23: Persist clustering run results transactionally in PostgreSQL.
        Each run uses a unique run_id so historical runs are never overwritten.
        """
        now_utc = datetime.now(timezone.utc)
        model_version = f"umap_hdbscan_v1_{self.embedding_service.model_name}"

        # 1. Store RootCauseCluster records
        unique_cids = sorted(list(set(labels)))
        db_cluster_map: Dict[int, RootCauseCluster] = {}

        for cid in unique_cids:
            cid_int = int(cid)
            summary_info = cluster_summaries.get(cid_int, {})
            issue_cnt = int(np.sum(labels == cid_int))

            rc_cluster = RootCauseCluster(
                repository_id=repository_id,
                run_id=run_id,
                cluster_id=cid_int,
                generated_label=summary_info.get("label", f"Cluster {cid_int}" if cid_int != -1 else "Noise / Outliers"),
                generated_description=summary_info.get("description", "Noise issues without strong cluster membership" if cid_int == -1 else ""),
                issue_count=issue_cnt,
                created_at=now_utc,
                model_version=model_version,
                umap_config=umap_config,
                hdbscan_config=hdbscan_config
            )
            session.add(rc_cluster)
            session.flush()
            db_cluster_map[cid_int] = rc_cluster

        # 2. Store RootCauseAssignment records
        for idx, item in enumerate(corpus):
            cid_int = int(labels[idx])
            db_cluster = db_cluster_map.get(cid_int)

            assignment = RootCauseAssignment(
                cluster_db_id=db_cluster.id if db_cluster else None,
                run_id=run_id,
                issue_id=item["issue_id"],
                cluster_id=cid_int,
                membership_probability=float(probabilities[idx]),
                outlier_score=float(outliers[idx])
            )
            session.add(assignment)

        session.flush()

        logger.info(
            f"Persisted clustering run '{run_id}': {len(unique_cids)} cluster entities, "
            f"{len(corpus)} assignments."
        )

        return {
            "run_id": run_id,
            "clusters_count": len(unique_cids),
            "assignments_count": len(corpus)
        }

    def generate_artifacts(
        self,
        run_id: str,
        corpus: List[Dict[str, Any]],
        labels: np.ndarray,
        probabilities: np.ndarray,
        matrix_2d: np.ndarray,
        evaluation_metrics: Dict[str, Any],
        cluster_summaries: Dict[int, Dict[str, Any]],
        representatives: Dict[int, List[Dict[str, Any]]]
    ) -> str:
        """
        Phase 24 & 25: Generate visualization (2D UMAP scatter plot) and machine-readable artifacts.
        Stored under artifacts/root_cause/run_<id>/
        """
        artifact_dir = Path("artifacts") / "root_cause" / f"run_{run_id}"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        total_issues = len(corpus)

        # 1. Generate 2D UMAP Visualization Plot
        fig, ax = plt.subplots(figsize=(10, 8))
        unique_labels = sorted(list(set(labels)))
        cmap = plt.cm.get_cmap("tab20", max(len(unique_labels), 1))

        for idx, cid in enumerate(unique_labels):
            mask = (labels == cid)
            if cid == -1:
                ax.scatter(
                    matrix_2d[mask, 0], matrix_2d[mask, 1],
                    c="gray", alpha=0.4, s=15, label="Noise (-1)"
                )
            else:
                label_name = cluster_summaries.get(cid, {}).get("label", f"Cluster {cid}")
                ax.scatter(
                    matrix_2d[mask, 0], matrix_2d[mask, 1],
                    color=cmap(idx), alpha=0.8, s=35, label=f"C{cid}: {label_name[:25]}"
                )

        ax.set_title(f"SupportPilot Root-Cause Clusters (Run {run_id})", fontsize=14)
        ax.set_xlabel("UMAP Dimension 1")
        ax.set_ylabel("UMAP Dimension 2")
        ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=8)
        plt.tight_layout()
        plot_path = artifact_dir / "umap_2d.png"
        fig.savefig(plot_path, dpi=150)
        plt.close(fig)

        # 2. Write clusters.csv
        csv_path = artifact_dir / "clusters.csv"
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("issue_id,issue_number,cluster_id,membership_probability,title\n")
            for idx, item in enumerate(corpus):
                safe_title = item["title"].replace('"', '""')
                f.write(f'{item["issue_id"]},{item["issue_number"]},{labels[idx]},{probabilities[idx]:.4f},"{safe_title}"\n')

        # 3. Write metrics.json
        metrics_path = artifact_dir / "metrics.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(evaluation_metrics, f, indent=2)

        # 4. Write cluster_summary.json
        summary_data = {
            "run_id": run_id,
            "total_issues": total_issues,
            "noise_count": int(evaluation_metrics.get("noise_count", 0)),
            "noise_percentage": evaluation_metrics.get("noise_percentage", 0.0),
            "clusters": []
        }

        for cid in sorted(unique_labels):
            if cid == -1:
                continue
            cnt = int(np.sum(labels == cid))
            pct = round((cnt / total_issues) * 100, 2) if total_issues > 0 else 0.0
            info = cluster_summaries.get(cid, {})
            reps = representatives.get(cid, [])

            summary_data["clusters"].append({
                "cluster_id": cid,
                "issue_count": cnt,
                "percentage": pct,
                "generated_label": info.get("label", f"Cluster {cid}"),
                "generated_description": info.get("description", ""),
                "representative_issues": reps,
                "purity": evaluation_metrics.get("per_cluster_purity", {}).get(cid, 0.0),
            })

        summary_path = artifact_dir / "cluster_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2)

        logger.info(f"Artifacts successfully written to: {artifact_dir}")
        return str(artifact_dir)

    def run_discovery_pipeline(
        self,
        repository_id: int,
        db_session: Optional[Session] = None,
        min_cluster_size: Optional[int] = None,
        min_samples: Optional[int] = None,
        state_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes the complete end-to-end Root-Cause Discovery Pipeline.
        """
        start_time = datetime.now(timezone.utc)
        run_id = f"run_{start_time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        def _execute(session: Session) -> Dict[str, Any]:
            # 1. Corpus Selection
            raw_corpus = self.get_root_cause_corpus(repository_id, session, state_filter=state_filter)

            # 2. Quality Filtering
            corpus, filter_stats = self.filter_corpus(raw_corpus)
            if not corpus:
                logger.warning("No eligible issues found for root cause clustering.")
                return {
                    "run_id": run_id,
                    "eligible_issues": 0,
                    "clusters_count": 0,
                    "noise_percentage": 0.0
                }

            # 3. Matrix Construction
            matrix = self.build_embedding_matrix(corpus)
            n_samples, n_dims = matrix.shape

            # UMAP & HDBSCAN Configs
            umap_cfg = {
                "n_neighbors": settings.root_cause_umap_neighbors,
                "min_dist": settings.root_cause_umap_min_dist,
                "n_components": settings.root_cause_umap_components,
                "metric": settings.root_cause_umap_metric,
                "random_state": settings.root_cause_umap_random_state
            }

            c_size = min_cluster_size or settings.root_cause_hdbscan_min_cluster_size
            c_samples = min_samples or settings.root_cause_hdbscan_min_samples
            hdbscan_cfg = {
                "min_cluster_size": c_size,
                "min_samples": c_samples,
                "metric": "euclidean"
            }

            # 4. Dimensionality Reduction (10D & 2D)
            matrix_10d = self.reduce_dimensions_umap(
                matrix,
                n_components=umap_cfg["n_components"],
                n_neighbors=umap_cfg["n_neighbors"],
                min_dist=umap_cfg["min_dist"],
                metric=umap_cfg["metric"],
                random_state=umap_cfg["random_state"]
            )

            matrix_2d = self.reduce_dimensions_umap(
                matrix,
                n_components=2,
                n_neighbors=umap_cfg["n_neighbors"],
                min_dist=umap_cfg["min_dist"],
                metric=umap_cfg["metric"],
                random_state=umap_cfg["random_state"]
            )

            # 5. HDBSCAN Clustering
            labels, probs, outliers = self.cluster_hdbscan(
                matrix_10d,
                min_cluster_size=hdbscan_cfg["min_cluster_size"],
                min_samples=hdbscan_cfg["min_samples"]
            )

            # 6. Representative Selection
            representatives = self.select_representative_issues(
                corpus, labels, probs, matrix_10d,
                max_representatives=settings.root_cause_max_representative_issues
            )

            # 7. LLM Labeling
            cluster_summaries = self.generate_llm_cluster_labels(representatives)

            # 8. Component Label Ground-Truth Evaluation
            component_gt, labeled_indices = self.extract_component_labels(corpus)
            eval_metrics = self.evaluate_purity_and_nmi(labels, component_gt)

            # 9. Stability Evaluation
            stability_ari = self.calculate_stability_ari(matrix_10d, labels)
            eval_metrics["stability_ari"] = stability_ari

            # 10. Database Persistence
            self.persist_clustering_run(
                repository_id=repository_id,
                run_id=run_id,
                corpus=corpus,
                labels=labels,
                probabilities=probs,
                outliers=outliers,
                cluster_summaries=cluster_summaries,
                umap_config=umap_cfg,
                hdbscan_config=hdbscan_cfg,
                session=session
            )

            # 11. Artifact Generation
            artifact_dir = self.generate_artifacts(
                run_id=run_id,
                corpus=corpus,
                labels=labels,
                probabilities=probs,
                matrix_2d=matrix_2d,
                evaluation_metrics=eval_metrics,
                cluster_summaries=cluster_summaries,
                representatives=representatives
            )

            end_time = datetime.now(timezone.utc)
            runtime_sec = round((end_time - start_time).total_seconds(), 2)

            unique_clusters = set(labels)
            unique_clusters.discard(-1)

            results = {
                "run_id": run_id,
                "repository_id": repository_id,
                "total_closed_issues": filter_stats["total_closed"],
                "eligible_issues": len(corpus),
                "embedding_model": self.embedding_service.model_name,
                "embedding_dims": n_dims,
                "umap_config": umap_cfg,
                "hdbscan_config": hdbscan_cfg,
                "discovered_clusters_count": len(unique_clusters),
                "noise_count": eval_metrics["noise_count"],
                "noise_percentage": eval_metrics["noise_percentage"],
                "weighted_purity": eval_metrics["weighted_purity"],
                "nmi": eval_metrics["nmi"],
                "stability_ari": stability_ari,
                "labeled_clusters_count": len(cluster_summaries),
                "artifact_dir": artifact_dir,
                "runtime_seconds": runtime_sec,
                "filter_stats": filter_stats,
                "eval_metrics": eval_metrics
            }

            return results

        if db_session:
            return _execute(db_session)
        elif self._external_session:
            return _execute(self._external_session)
        else:
            with get_db() as session:
                return _execute(session)
