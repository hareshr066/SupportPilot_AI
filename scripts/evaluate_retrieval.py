import sys
import math
import logging
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set, Tuple

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.session import get_db
from app.database.models import Repository, Issue, RetrievalEvaluationRun
from app.services.hybrid_retrieval_service import HybridRetrievalService
from sqlalchemy import select

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("evaluate_retrieval")


def calculate_mrr(retrieved_ids: List[int], ground_truth_ids: Set[int], k: int = 10) -> float:
    """Calculates Mean Reciprocal Rank (MRR@K)."""
    for rank, item_id in enumerate(retrieved_ids[:k], 1):
        if item_id in ground_truth_ids:
            return 1.0 / rank
    return 0.0


def calculate_recall(retrieved_ids: List[int], ground_truth_ids: Set[int], k: int) -> float:
    """Calculates Recall@K."""
    if not ground_truth_ids:
        return 0.0
    retrieved_k = set(retrieved_ids[:k])
    hits = len(retrieved_k.intersection(ground_truth_ids))
    return hits / float(len(ground_truth_ids))


def calculate_ndcg(retrieved_ids: List[int], ground_truth_grades: Dict[int, float], k: int = 10) -> float:
    """Calculates nDCG@K with graded relevance."""
    if not ground_truth_grades:
        return 0.0

    dcg = 0.0
    for rank, item_id in enumerate(retrieved_ids[:k], 1):
        rel = ground_truth_grades.get(item_id, 0.0)
        if rel > 0:
            dcg += (2.0 ** rel - 1.0) / math.log2(rank + 1)

    # Calculate Ideal DCG (IDCG)
    ideal_rels = sorted(ground_truth_grades.values(), reverse=True)[:k]
    idcg = 0.0
    for rank, rel in enumerate(ideal_rels, 1):
        if rel > 0:
            idcg += (2.0 ** rel - 1.0) / math.log2(rank + 1)

    return (dcg / idcg) if idcg > 0 else 0.0


def evaluate_retrieval_pipeline(
    session,
    repository_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Runs evaluation of BM25-only, Dense-only, and Hybrid retrieval modes
    using temporal filtering (`candidate.created_at < query_issue.created_at`).
    """
    service = HybridRetrievalService(db_session=session)
    service.load_or_build_bm25_index(session, repository_id=repository_id)

    # Select queries that have a ground-truth duplicate relationship or closed reference
    q = select(Issue).where(Issue.duplicate_of_issue_number.isnot(None))
    if repository_id is not None:
        q = q.where(Issue.repository_id == repository_id)

    eval_issues = session.scalars(q).all()

    # Fallback to evaluating all available closed issues if explicit ground truth is small
    if len(eval_issues) < 2:
        logger.warning(
            f"Only {len(eval_issues)} explicit duplicate ground-truth issues found. "
            f"Falling back to evaluating all available issues against component families."
        )
        q_all = select(Issue)
        if repository_id is not None:
            q_all = q_all.where(Issue.repository_id == repository_id)
        eval_issues = session.scalars(q_all).all()

    bm25_r5, bm25_r10, bm25_mrr = [], [], []
    dense_r5, dense_r10, dense_mrr = [], [], []
    hybrid_r5, hybrid_r10, hybrid_mrr, hybrid_ndcg = [], [], [], []

    failure_examples = []

    for query_iss in eval_issues:
        query_text = f"{query_iss.title}\n{query_iss.body}"

        # Identify ground-truth target issues
        gt_ids = set()
        gt_grades = {}

        if query_iss.duplicate_of_issue_number:
            target = session.scalar(
                select(Issue).where(
                    Issue.repository_id == query_iss.repository_id,
                    Issue.issue_number == query_iss.duplicate_of_issue_number
                )
            )
            if target and target.id != query_iss.id:
                gt_ids.add(target.id)
                gt_grades[target.id] = 1.0

        # Also include issues sharing same component labels as weak ground truth (grade 0.5)
        query_labels = set(l.name for l in query_iss.labels)
        if query_labels:
            same_label_issues = session.scalars(
                select(Issue).where(
                    Issue.repository_id == query_iss.repository_id,
                    Issue.id != query_iss.id
                )
            ).all()
            for other in same_label_issues:
                other_labels = set(l.name for l in other.labels)
                if query_labels.intersection(other_labels):
                    if other.id not in gt_ids:
                        gt_ids.add(other.id)
                        gt_grades[other.id] = 0.5

        if not gt_ids:
            continue

        # Generate query embedding
        query_emb = service.embedding_service.generate_text_embedding(query_text)
        temporal_cutoff = query_iss.created_at

        # 1. BM25-only retrieval
        bm25_res = service.retrieve_bm25(
            query_text, session, repository_id=repository_id, top_k=10, temporal_cutoff=temporal_cutoff
        )
        bm25_ids = [iss_id for iss_id, _ in bm25_res if iss_id != query_iss.id]

        # 2. Dense-only retrieval
        dense_res = service.retrieve_dense(
            query_emb, session, repository_id=repository_id, top_k=10, temporal_cutoff=temporal_cutoff
        )
        dense_ids = [iss_id for iss_id, _ in dense_res if iss_id != query_iss.id]

        # 3. Hybrid retrieval
        hybrid_res = service.retrieve_resolved_cases(
            query_text, repository_id=repository_id, query_issue_id=query_iss.id,
            top_k=10, temporal_cutoff=temporal_cutoff, db_session=session
        )
        hybrid_ids = [res["issue_id"] for res in hybrid_res]

        # Metrics for BM25
        bm25_r5.append(calculate_recall(bm25_ids, gt_ids, 5))
        bm25_r10.append(calculate_recall(bm25_ids, gt_ids, 10))
        bm25_mrr.append(calculate_mrr(bm25_ids, gt_ids, 10))

        # Metrics for Dense
        dense_r5.append(calculate_recall(dense_ids, gt_ids, 5))
        dense_r10.append(calculate_recall(dense_ids, gt_ids, 10))
        dense_mrr.append(calculate_mrr(dense_ids, gt_ids, 10))

        # Metrics for Hybrid
        h_r5 = calculate_recall(hybrid_ids, gt_ids, 5)
        h_r10 = calculate_recall(hybrid_ids, gt_ids, 10)
        h_mrr = calculate_mrr(hybrid_ids, gt_ids, 10)
        h_ndcg = calculate_ndcg(hybrid_ids, gt_grades, 10)

        hybrid_r5.append(h_r5)
        hybrid_r10.append(h_r10)
        hybrid_mrr.append(h_mrr)
        hybrid_ndcg.append(h_ndcg)

        # Track failure cases for failure analysis
        b_mrr = calculate_mrr(bm25_ids, gt_ids, 10)
        d_mrr = calculate_mrr(dense_ids, gt_ids, 10)
        if (b_mrr > 0 and d_mrr == 0) or (d_mrr > 0 and b_mrr == 0) or (h_mrr > max(b_mrr, d_mrr)):
            failure_examples.append({
                "query_issue_id": query_iss.id,
                "query_title": query_iss.title,
                "bm25_mrr": b_mrr,
                "dense_mrr": d_mrr,
                "hybrid_mrr": h_mrr,
            })

    eval_count = len(bm25_r5)

    metrics = {
        "eval_query_count": eval_count,
        "bm25": {
            "recall_5": round(float(np.mean(bm25_r5)), 4) if eval_count > 0 else 0.0,
            "recall_10": round(float(np.mean(bm25_r10)), 4) if eval_count > 0 else 0.0,
            "mrr_10": round(float(np.mean(bm25_mrr)), 4) if eval_count > 0 else 0.0,
        },
        "dense": {
            "recall_5": round(float(np.mean(dense_r5)), 4) if eval_count > 0 else 0.0,
            "recall_10": round(float(np.mean(dense_r10)), 4) if eval_count > 0 else 0.0,
            "mrr_10": round(float(np.mean(dense_mrr)), 4) if eval_count > 0 else 0.0,
        },
        "hybrid": {
            "recall_5": round(float(np.mean(hybrid_r5)), 4) if eval_count > 0 else 0.0,
            "recall_10": round(float(np.mean(hybrid_r10)), 4) if eval_count > 0 else 0.0,
            "mrr_10": round(float(np.mean(hybrid_mrr)), 4) if eval_count > 0 else 0.0,
            "ndcg_10": round(float(np.mean(hybrid_ndcg)), 4) if eval_count > 0 else 0.0,
        },
        "failure_examples_count": len(failure_examples)
    }

    # Record evaluation run in PostgreSQL
    now_utc = datetime.now(timezone.utc)
    eval_run_id = f"eval_{now_utc.strftime('%Y%m%d_%H%M%S')}"

    eval_record = RetrievalEvaluationRun(
        eval_run_id=eval_run_id,
        repository_id=repository_id,
        eval_query_count=eval_count,
        bm25_recall_5=metrics["bm25"]["recall_5"],
        bm25_recall_10=metrics["bm25"]["recall_10"],
        bm25_mrr_10=metrics["bm25"]["mrr_10"],
        dense_recall_5=metrics["dense"]["recall_5"],
        dense_recall_10=metrics["dense"]["recall_10"],
        dense_mrr_10=metrics["dense"]["mrr_10"],
        hybrid_recall_5=metrics["hybrid"]["recall_5"],
        hybrid_recall_10=metrics["hybrid"]["recall_10"],
        hybrid_mrr_10=metrics["hybrid"]["mrr_10"],
        hybrid_ndcg_10=metrics["hybrid"]["ndcg_10"],
        created_at=now_utc,
        metadata_info={"temporal_filtering": True, "eval_count": eval_count}
    )
    session.add(eval_record)
    session.flush()

    metrics["eval_run_id"] = eval_run_id
    return metrics


def main():
    parser = argparse.ArgumentParser(
        description="SupportPilot - Evaluate Hybrid Retrieval Performance"
    )
    parser.add_argument("--owner", type=str, default="microsoft", help="Repository owner")
    parser.add_argument("--repo", type=str, default="vscode", help="Repository name")

    args = parser.parse_args()
    full_name = f"{args.owner}/{args.repo}"
    logger.info(f"Running Retrieval Evaluation for repository: {full_name}")

    with get_db() as session:
        repo = session.scalar(
            select(Repository).where(Repository.full_name == full_name)
        )
        repo_id = repo.id if repo else None

        results = evaluate_retrieval_pipeline(session, repository_id=repo_id)

        print("\n=======================================================================")
        print("                 RETRIEVAL EVALUATION RESULTS                          ")
        print("=======================================================================")
        print(f"  Eval Run ID:         {results['eval_run_id']}")
        print(f"  Evaluated Queries:   {results['eval_query_count']}")
        print("-----------------------------------------------------------------------")
        print("  METRIC             | BM25-ONLY   | DENSE-ONLY  | HYBRID (RRF)")
        print("-----------------------------------------------------------------------")
        print(f"  Recall@5           | {results['bm25']['recall_5']:<11.4f} | {results['dense']['recall_5']:<11.4f} | {results['hybrid']['recall_5']:<11.4f}")
        print(f"  Recall@10          | {results['bm25']['recall_10']:<11.4f} | {results['dense']['recall_10']:<11.4f} | {results['hybrid']['recall_10']:<11.4f}")
        print(f"  MRR@10             | {results['bm25']['mrr_10']:<11.4f} | {results['dense']['mrr_10']:<11.4f} | {results['hybrid']['mrr_10']:<11.4f}")
        print(f"  nDCG@10            | N/A         | N/A         | {results['hybrid']['ndcg_10']:<11.4f}")
        print("=======================================================================\n")


if __name__ == "__main__":
    main()
