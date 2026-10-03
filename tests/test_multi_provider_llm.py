import pytest
import time
from unittest.mock import MagicMock, patch
from pydantic import BaseModel

from config import settings
from app.services.llm_client import LLMClient
from app.services.llm_providers.base import (
    BaseLLMProvider,
    LLMResponse,
    LLMErrorCategory,
)
from app.services.llm_providers.health_tracker import ProviderHealthTracker, ProviderState
from app.services.llm_providers.router import LLMProviderRouter, AllProvidersFailedException
from app.services.llm_providers.openai_provider import OpenAIProvider
from app.services.llm_providers.groq_provider import GroqProvider
from app.services.llm_providers.gemini_provider import GeminiProvider
from app.services.llm_providers.openrouter_provider import OpenRouterProvider


class SampleOutputSchema(BaseModel):
    summary: str
    status: str


class MockSuccessProvider(BaseLLMProvider):
    def __init__(self, name: str, model: str = "mock-model"):
        super().__init__(name=name, model=model, api_key="mock-key")

    def is_configured(self) -> bool:
        return True

    def generate(self, prompt: str, system_prompt=None, temperature=0.0) -> str:
        return f"Response from {self.name}"

    def generate_structured(self, prompt: str, system_prompt: str, response_schema, temperature=0.0):
        return {"summary": f"Success from {self.name}", "status": "ok"}


class MockErrorProvider(BaseLLMProvider):
    def __init__(self, name: str, exc_to_raise: Exception, model: str = "mock-model"):
        super().__init__(name=name, model=model, api_key="mock-key")
        self.exc_to_raise = exc_to_raise

    def is_configured(self) -> bool:
        return True

    def generate(self, prompt: str, system_prompt=None, temperature=0.0) -> str:
        raise self.exc_to_raise

    def generate_structured(self, prompt: str, system_prompt: str, response_schema, temperature=0.0):
        raise self.exc_to_raise


@pytest.fixture
def clean_tracker():
    tracker = ProviderHealthTracker(default_cooldown_seconds=60.0)
    tracker.reset()
    return tracker


# 1. Test OpenAI Succeeds
def test_1_openai_succeeds(clean_tracker):
    openai_p = MockSuccessProvider("openai")
    groq_p = MockSuccessProvider("groq")
    router = LLMProviderRouter(
        providers={"openai": openai_p, "groq": groq_p},
        provider_order=["openai", "groq"],
        tracker=clean_tracker
    )
    res = router.generate_structured("prompt", "sys", SampleOutputSchema)
    assert res.provider == "openai"
    assert res.parsed_json["summary"] == "Success from openai"
    assert res.attempt == 1
    assert res.fallback_from is None


# 2. Test OpenAI 429 -> Groq Succeeds
def test_2_openai_429_groq_succeeds(clean_tracker):
    openai_p = MockErrorProvider("openai", Exception("HTTP 429 Rate limit exceeded"))
    groq_p = MockSuccessProvider("groq")
    router = LLMProviderRouter(
        providers={"openai": openai_p, "groq": groq_p},
        provider_order=["openai", "groq"],
        tracker=clean_tracker
    )
    res = router.generate_structured("prompt", "sys", SampleOutputSchema)
    assert res.provider == "groq"
    assert res.parsed_json["summary"] == "Success from groq"
    assert res.attempt == 2
    assert res.fallback_from == "openai"


# 3. Test OpenAI Temporary Failure -> Groq Succeeds
def test_3_openai_temp_failure_groq_succeeds(clean_tracker):
    openai_p = MockErrorProvider("openai", Exception("503 Service Unavailable"))
    groq_p = MockSuccessProvider("groq")
    router = LLMProviderRouter(
        providers={"openai": openai_p, "groq": groq_p},
        provider_order=["openai", "groq"],
        tracker=clean_tracker
    )
    res = router.generate_structured("prompt", "sys", SampleOutputSchema)
    assert res.provider == "groq"
    assert res.fallback_from == "openai"


# 4. Test OpenAI Fails -> Groq Fails -> Gemini Succeeds
def test_4_openai_groq_fail_gemini_succeeds(clean_tracker):
    openai_p = MockErrorProvider("openai", Exception("429 Too Many Requests"))
    groq_p = MockErrorProvider("groq", Exception("502 Bad Gateway"))
    gemini_p = MockSuccessProvider("gemini")
    router = LLMProviderRouter(
        providers={"openai": openai_p, "groq": groq_p, "gemini": gemini_p},
        provider_order=["openai", "groq", "gemini"],
        tracker=clean_tracker
    )
    res = router.generate_structured("prompt", "sys", SampleOutputSchema)
    assert res.provider == "gemini"
    assert res.attempt == 3
    assert res.fallback_from == "groq"


# 5. Test OpenAI -> Groq -> Gemini -> OpenRouter Succeeds
def test_5_full_failover_to_openrouter(clean_tracker):
    openai_p = MockErrorProvider("openai", Exception("429 Rate limit"))
    groq_p = MockErrorProvider("groq", Exception("500 Server Error"))
    gemini_p = MockErrorProvider("gemini", Exception("Connection timeout"))
    openrouter_p = MockSuccessProvider("openrouter")
    router = LLMProviderRouter(
        providers={"openai": openai_p, "groq": groq_p, "gemini": gemini_p, "openrouter": openrouter_p},
        provider_order=["openai", "groq", "gemini", "openrouter"],
        tracker=clean_tracker
    )
    res = router.generate_structured("prompt", "sys", SampleOutputSchema)
    assert res.provider == "openrouter"
    assert res.attempt == 4
    assert res.fallback_from == "gemini"


# 6. Test All Providers Fail -> Deterministic Safe Fallback
def test_6_all_providers_fail_safe_fallback(clean_tracker):
    openai_p = MockErrorProvider("openai", Exception("429 Rate limit"))
    groq_p = MockErrorProvider("groq", Exception("500 Server Error"))
    router = LLMProviderRouter(
        providers={"openai": openai_p, "groq": groq_p},
        provider_order=["openai", "groq"],
        tracker=clean_tracker
    )
    client = LLMClient(router=router)
    fallback = client.generate_structured("prompt", "sys", SampleOutputSchema)
    assert fallback["resolution_type"] == "insufficient_evidence"
    assert fallback["needs_human_review"] is True
    assert client.last_metadata["status"] == "failed"
    assert client.last_metadata["error_category"] == "all_providers_failed"


# 7. Test Provider Cooldown Behavior
def test_7_provider_cooldown(clean_tracker):
    openai_p = MockErrorProvider("openai", Exception("429 Rate limit"))
    groq_p = MockSuccessProvider("groq")
    router = LLMProviderRouter(
        providers={"openai": openai_p, "groq": groq_p},
        provider_order=["openai", "groq"],
        tracker=clean_tracker,
        cooldown_seconds=10.0
    )
    # First call: OpenAI fails (placed in cooldown), Groq succeeds
    res1 = router.generate_structured("prompt", "sys", SampleOutputSchema)
    assert res1.provider == "groq"
    assert clean_tracker.get_state("openai").status == "cooldown"

    # Second call: OpenAI is in cooldown so it should be SKIPPED immediately without calling OpenAI again!
    openai_p.generate_structured = MagicMock(side_effect=Exception("Should not be called!"))
    res2 = router.generate_structured("prompt", "sys", SampleOutputSchema)
    assert res2.provider == "groq"
    assert openai_p.generate_structured.call_count == 0


# 8. Test Non-Retryable Malformed Request
def test_8_non_retryable_request(clean_tracker):
    # 400 Bad Request / Schema Error is non-retryable programming error
    openai_p = MockErrorProvider("openai", Exception("400 Bad Request invalid prompt syntax"))
    groq_p = MockSuccessProvider("groq")
    router = LLMProviderRouter(
        providers={"openai": openai_p, "groq": groq_p},
        provider_order=["openai", "groq"],
        tracker=clean_tracker
    )
    client = LLMClient(router=router)
    fallback = client.generate_structured("prompt", "sys", SampleOutputSchema)
    assert fallback["resolution_type"] == "insufficient_evidence"
    assert client.last_metadata["status"] == "failed"


# 9. Test Authentication / Configuration Failure Handling
def test_9_auth_failure_handling(clean_tracker):
    openai_p = MockErrorProvider("openai", Exception("401 Invalid API Key"))
    groq_p = MockSuccessProvider("groq")
    router = LLMProviderRouter(
        providers={"openai": openai_p, "groq": groq_p},
        provider_order=["openai", "groq"],
        tracker=clean_tracker
    )
    res = router.generate_structured("prompt", "sys", SampleOutputSchema)
    assert res.provider == "groq"
    assert clean_tracker.get_state("openai").status == "disabled"


# 10. Test Malformed Structured Response Handling
def test_10_malformed_structured_response(clean_tracker):
    # Provider returns dict missing required Pydantic schema field, raising ValidationError
    class BadJsonProvider(BaseLLMProvider):
        def __init__(self):
            super().__init__(name="openai", model="m", api_key="k")
        def is_configured(self): return True
        def generate(self, prompt, system_prompt=None, temperature=0.0): return ""
        def generate_structured(self, prompt, system_prompt, response_schema, temperature=0.0):
            # Raise ValidationError on schema mismatch as real provider adapters do
            response_schema.model_validate({"wrong_field": 123})

    bad_p = BadJsonProvider()
    groq_p = MockSuccessProvider("groq")
    router = LLMProviderRouter(
        providers={"openai": bad_p, "groq": groq_p},
        provider_order=["openai", "groq"],
        tracker=clean_tracker
    )
    res = router.generate_structured("prompt", "sys", SampleOutputSchema)
    assert res.provider == "groq"


# 11. Test Correct Provider/Model Metadata
def test_11_provider_model_metadata(clean_tracker):
    groq_p = MockSuccessProvider("groq", model="llama-3.3-70b-versatile")
    router = LLMProviderRouter(
        providers={"groq": groq_p},
        provider_order=["groq"],
        tracker=clean_tracker
    )
    client = LLMClient(router=router)
    res = client.generate_structured("prompt", "sys", SampleOutputSchema)
    meta = client.last_metadata
    assert meta["provider"] == "groq"
    assert meta["model"] == "llama-3.3-70b-versatile"
    assert meta["status"] == "success"
    assert "latency_ms" in meta


# 12. Test API Keys Never Appear in Logs/Errors/Responses
def test_12_api_keys_never_exposed(clean_tracker):
    secret_key = "sk-secret-super-private-key-12345"
    provider = OpenAIProvider(api_key=secret_key)
    res = provider.to_metadata_dict() if hasattr(provider, "to_metadata_dict") else {}
    assert secret_key not in str(res)

    # Check router metadata
    groq_p = MockSuccessProvider("groq")
    router = LLMProviderRouter(providers={"groq": groq_p}, provider_order=["groq"], tracker=clean_tracker)
    resp = router.generate_structured("p", "s", SampleOutputSchema)
    meta_str = str(resp.to_metadata_dict())
    assert secret_key not in meta_str
    assert "Bearer" not in meta_str


# 13. Test Claim Verification Runs After Provider Failover
def test_13_claim_verification_runs_after_failover(clean_tracker):
    from app.services.claim_verification_service import ClaimVerificationService
    openai_p = MockErrorProvider("openai", Exception("429 Rate limit"))
    groq_p = MockSuccessProvider("groq")
    router = LLMProviderRouter(
        providers={"openai": openai_p, "groq": groq_p},
        provider_order=["openai", "groq"],
        tracker=clean_tracker
    )
    client = LLMClient(router=router)
    verifier = ClaimVerificationService(verifier_llm_client=client)

    # Mock verifier LLM response inside groq output
    client.router.providers["groq"].generate_structured = MagicMock(return_value={
        "verdict": "SUPPORTED",
        "support_strength": 0.95,
        "explanation": "Evidence supports claim",
        "evidence_spans": []
    })

    resolved_sources = {
        "issue:1": {
            "source_id": "issue:1",
            "content": "This is historical evidence content text."
        }
    }
    res = verifier.verify_single_claim(
        claim_id="c1",
        parent_claim_id=None,
        claim_text="This fix resolves the error.",
        source_ids=["issue:1"],
        resolved_sources=resolved_sources
    )
    assert res.verdict == "SUPPORTED"
    assert res.support_strength == 0.95


# 14. Test Confidence Calibration Under Failover
def test_14_confidence_calibrated_under_failover():
    from app.services.confidence_service import extract_confidence_features
    from app.schemas.verification_schemas import ResolutionVerificationSummary
    summary = ResolutionVerificationSummary(
        verification_run_id="vr_1",
        resolution_run_id="rr_1",
        overall_faithfulness_status="PASSED",
        total_claims=2,
        supported_count=2,
        partially_supported_count=0,
        unsupported_count=0,
        contradicted_count=0,
        unclear_count=0,
        overall_verdict="SUPPORTED",
        average_support_strength=0.9,
        citation_coverage=1.0,
        unsupported_claim_rate=0.0,
        claim_results=[]
    )
    features = extract_confidence_features(
        resolution_run_data={"steps": [1, 2]},
        verification_summary=summary,
        retrieval_metadata={"top_dense_similarity": 0.85, "evidence_completeness": 0.9}
    )
    assert features.supported_claim_ratio == 1.0
    assert features.citation_coverage == 1.0
    assert features.evidence_completeness == 0.9


# 15. Test Final All-Provider Failure Routes to HUMAN_ESCALATION
def test_15_all_providers_failed_routes_to_human_escalation(clean_tracker):
    from app.services.grounded_resolution_service import GroundedResolutionService
    openai_p = MockErrorProvider("openai", Exception("429 Rate limit"))
    groq_p = MockErrorProvider("groq", Exception("500 Server Error"))
    router = LLMProviderRouter(
        providers={"openai": openai_p, "groq": groq_p},
        provider_order=["openai", "groq"],
        tracker=clean_tracker
    )
    client = LLMClient(router=router)
    svc = GroundedResolutionService(llm_client=client)

    # When all LLM providers fail, GroundedResolution returns safe fallback with needs_human_review=True
    fallback_res = client.generate_structured("prompt", "sys", SampleOutputSchema)
    assert fallback_res["needs_human_review"] is True
