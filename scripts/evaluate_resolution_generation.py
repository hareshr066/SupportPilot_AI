import sys
import logging
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from app.database.session import get_db
from app.database.models import Repository, Issue
from app.schemas.resolution_schemas import ResolutionRequest
from app.services.grounded_resolution_service import GroundedResolutionService
from app.services.embedding_service import EmbeddingService
from sqlalchemy import select

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("evaluate_resolution_generation")


def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Computes cosine similarity between two embedding vectors."""
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def evaluate_grounded_resolution_pipeline(
    session,
    repository_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Evaluates Grounded Resolution Generation pipeline against closed historical issues
    with strict temporal filtering (`closed_at < query.created_at`).
    """
    embedding_service = EmbeddingService(model_name=settings.embedding_model_name)
    service = GroundedResolutionService(db_session=session)

    # Select closed issues that have resolution/closing comments or linked PRs
    q = select(Issue).where(Issue.state == "closed")
    if repository_id is not None:
        q = q.where(Issue.repository_id == repository_id)

    eval_issues = session.scalars(q).all()

    if not eval_issues:
        logger.warning("No closed issues found for resolution generation evaluation.")
        return {
            "eval_query_count": 0,
            "mean_semantic_similarity_llm": 0.0,
            "mean_semantic_similarity_raw_baseline": 0.0,
            "mean_citation_coverage": 0.0,
            "mean_unsupported_claim_rate": 0.0
        }

    sim_llm_list = []
    sim_baseline_list = []
    citation_coverage_list = []
    unsupported_rate_list = []

    for query_iss in eval_issues:
        # Extract ground-truth fix text from issue closing comment or PRs
        gt_fix_parts = []
        for c in query_iss.comments:
            c_lower = c.body.lower()
            if any(kw in c_lower for kw in ["fixed", "resolved", "pr #", "merged"]):
                gt_fix_parts.append(c.body)

        for pr in query_iss.pull_requests:
            gt_fix_parts.append(f"PR #{pr.pr_number}")

        if not gt_fix_parts:
            # Fallback to last comment as ground truth fix
            if query_iss.comments:
                gt_fix_parts.append(query_iss.comments[-1].body)
            else:
                continue

        gt_fix_text = "\n".join(gt_fix_parts)
        gt_emb = embedding_service.generate_text_embedding(gt_fix_text)

        request = ResolutionRequest(
            title=query_iss.title,
            body=query_iss.body or "",
            repository_id=query_iss.repository_id,
            issue_number=query_iss.issue_number
        )

        res, evidence_pkg, run_id = service.generate_resolution(
            request=request,
            session=session
        )

        # Generated resolution embedding
        gen_text = f"{res.summary}\n{res.diagnosis}\n{res.recommended_resolution}"
        gen_emb = embedding_service.generate_text_embedding(gen_text)

        llm_sim = compute_cosine_similarity(gen_emb, gt_emb)
        sim_llm_list.append(llm_sim)

        # Baseline: Raw top retrieved case text without LLM synthesis
        if evidence_pkg.cases:
            top_case = evidence_pkg.cases[0]
            base_text = f"{top_case.title}\n{top_case.resolution_snippet}"
            base_emb = embedding_service.generate_text_embedding(base_text)
            base_sim = compute_cosine_similarity(base_emb, gt_emb)
        else:
            base_sim = 0.0

        sim_baseline_list.append(base_sim)
        citation_coverage_list.append(res.citation_coverage)
        unsupported_rate_list.append(res.unsupported_claim_rate)

    eval_count = len(sim_llm_list)

    return {
        "eval_query_count": eval_count,
        "mean_semantic_similarity_llm": round(float(np.mean(sim_llm_list)), 4) if eval_count > 0 else 0.0,
        "mean_semantic_similarity_raw_baseline": round(float(np.mean(sim_baseline_list)), 4) if eval_count > 0 else 0.0,
        "mean_citation_coverage": round(float(np.mean(citation_coverage_list)), 4) if eval_count > 0 else 0.0,
        "mean_unsupported_claim_rate": round(float(np.mean(unsupported_rate_list)), 4) if eval_count > 0 else 0.0
    }


def main():
    parser = argparse.ArgumentParser(
        description="SupportPilot - Evaluate Grounded Resolution Generation Pipeline"
    )
    parser.add_argument("--owner", type=str, default="microsoft", help="Repository owner")
    parser.add_argument("--repo", type=str, default="vscode", help="Repository name")

    args = parser.parse_args()
    full_name = f"{args.owner}/{args.repo}"
    logger.info(f"Running Resolution Generation Evaluation for repository: {full_name}")

    with get_db() as session:
        repo = session.scalar(
            select(Repository).where(Repository.full_name == full_name)
        )
        repo_id = repo.id if repo else None

        results = evaluate_grounded_resolution_pipeline(session, repository_id=repo_id)

        print("\n=======================================================================")
        print("           GROUNDED RESOLUTION GENERATION EVALUATION                   ")
        print("=======================================================================")
        print(f"  Evaluated Queries:              {results['eval_query_count']}")
        print("-----------------------------------------------------------------------")
        print(f"  LLM Semantic Similarity:       {results['mean_semantic_similarity_llm']:.4f}")
        print(f"  Raw Baseline Similarity:        {results['mean_semantic_similarity_raw_baseline']:.4f}")
        print(f"  Citation Coverage:             {results['mean_citation_coverage'] * 100:.1f}%")
        print(f"  Unsupported Claim Rate:        {results['mean_unsupported_claim_rate'] * 100:.1f}%")
        print("=======================================================================\n")


if __name__ == "__main__":
    main()
