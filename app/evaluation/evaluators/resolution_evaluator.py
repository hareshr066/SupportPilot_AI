import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.evaluation.dataset import EvaluationDatasetItem
from app.services.grounded_resolution_service import GroundedResolutionService
from app.services.claim_verification_service import ClaimVerificationService
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

def compute_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class ResolutionEvaluator:
    """
    Evaluates Grounded Resolution Generation and Claim Verification / Faithfulness.
    Combines semantic similarity, step overlap, and claim verification outputs.
    """

    def __init__(
        self,
        resolution_service: Optional[GroundedResolutionService] = None,
        verification_service: Optional[ClaimVerificationService] = None,
        embedding_service: Optional[EmbeddingService] = None
    ):
        self.resolution_service = resolution_service or GroundedResolutionService()
        self.verification_service = verification_service or ClaimVerificationService()
        self.embedding_service = embedding_service or EmbeddingService()

    def evaluate(
        self,
        test_items: List[EvaluationDatasetItem],
        db_session: Session
    ) -> Dict[str, Any]:
        valid_items = [it for it in test_items if it.resolution_ground_truth]
        sample_count = len(valid_items)

        if sample_count < 1:
            return {
                "status": "INSUFFICIENT_EVALUATION_DATA",
                "sample_count": 0,
                "reason": "No test tickets with accepted resolution ground truth available."
            }

        total_supported = 0
        total_unsupported = 0
        total_contradicted = 0
        total_claims = 0
        total_citation_coverage = 0.0
        semantic_scores = []
        resolution_correct_count = 0

        for it in valid_items:
            try:
                # Generate resolution
                res_output = self.resolution_service.generate_resolution(
                    ticket_id=it.ticket_id,
                    title=it.title,
                    body=it.body,
                    repository_id=it.repository_id,
                    db_session=db_session
                )

                # Verify claims
                ver_output = self.verification_service.verify_resolution_claims(
                    resolution_summary=res_output.summary,
                    claims=res_output.raw_claims,
                    retrieved_evidence=res_output.evidence_cases,
                    db_session=db_session
                )

                # Accumulate claim metrics
                n_claims = ver_output.total_claims
                total_claims += n_claims
                total_supported += ver_output.supported_count
                total_unsupported += ver_output.unsupported_count
                total_contradicted += ver_output.contradicted_count
                total_citation_coverage += ver_output.citation_coverage

                # Calculate semantic match against historical fix
                gen_text = f"{res_output.summary} {res_output.recommended_action}"
                truth_text = it.resolution_ground_truth or ""

                gen_emb = self.embedding_service.generate_embedding(gen_text)
                truth_emb = self.embedding_service.generate_embedding(truth_text)
                sim = compute_cosine_similarity(gen_emb, truth_emb)
                semantic_scores.append(sim)

                # Resolution correctness rule: semantic similarity >= 0.70 AND faithfulness >= 0.75 AND no critical failures
                faithfulness = (ver_output.supported_count / n_claims) if n_claims > 0 else 1.0
                is_correct = (sim >= 0.70) and (faithfulness >= 0.75) and not ver_output.has_critical_failure

                if is_correct:
                    resolution_correct_count += 1

            except Exception as e:
                logger.warning(f"Resolution evaluation error for ticket {it.ticket_id}: {e}")

        overall_faithfulness_rate = (total_supported / total_claims) if total_claims > 0 else 0.0
        unsupported_rate = (total_unsupported / total_claims) if total_claims > 0 else 0.0
        contradiction_rate = (total_contradicted / total_claims) if total_claims > 0 else 0.0
        mean_semantic_similarity = (sum(semantic_scores) / len(semantic_scores)) if semantic_scores else 0.0
        correctness_rate = (resolution_correct_count / sample_count) if sample_count > 0 else 0.0
        avg_citation_coverage = (total_citation_coverage / sample_count) if sample_count > 0 else 0.0

        return {
            "status": "COMPLETED",
            "sample_count": sample_count,
            "total_factual_claims_evaluated": total_claims,
            "supported_claims_count": total_supported,
            "unsupported_claims_count": total_unsupported,
            "contradicted_claims_count": total_contradicted,
            "faithfulness_rate": round(overall_faithfulness_rate, 4),
            "unsupported_claim_rate": round(unsupported_rate, 4),
            "contradiction_rate": round(contradiction_rate, 4),
            "citation_coverage": round(avg_citation_coverage, 4),
            "mean_semantic_similarity": round(mean_semantic_similarity, 4),
            "resolution_correctness_rate": round(correctness_rate, 4),
            "resolution_correctness_count": resolution_correct_count
        }
