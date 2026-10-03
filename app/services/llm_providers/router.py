import time
import logging
from typing import Dict, List, Any, Optional, Type
from pydantic import BaseModel
from config import settings
from app.services.llm_providers.base import (
    BaseLLMProvider,
    LLMResponse,
    LLMErrorCategory,
    classify_exception,
    is_retryable_error,
)
from app.services.llm_providers.health_tracker import (
    ProviderHealthTracker,
    health_tracker as global_health_tracker,
)
from app.services.llm_providers.openai_provider import OpenAIProvider
from app.services.llm_providers.groq_provider import GroqProvider
from app.services.llm_providers.gemini_provider import GeminiProvider
from app.services.llm_providers.openrouter_provider import OpenRouterProvider

logger = logging.getLogger("llm_providers.router")


class AllProvidersFailedException(Exception):
    """Raised when every configured LLM provider in the failover chain has failed."""
    pass


class LLMProviderRouter:
    """
    Provider-Agnostic LLM Orchestrator and Failover Router for SupportPilot.
    Enforces priority-based failover, classified error handling, cooldown isolation,
    and safe execution telemetry.
    """

    def __init__(
        self,
        providers: Optional[Dict[str, BaseLLMProvider]] = None,
        provider_order: Optional[List[str]] = None,
        tracker: Optional[ProviderHealthTracker] = None,
        cooldown_seconds: Optional[float] = None
    ):
        self.tracker = tracker or global_health_tracker
        self.cooldown_seconds = cooldown_seconds or settings.llm_cooldown_seconds

        # Instantiate default providers
        self.providers: Dict[str, BaseLLMProvider] = providers or {
            "openai": OpenAIProvider(),
            "groq": GroqProvider(),
            "gemini": GeminiProvider(),
            "openrouter": OpenRouterProvider(),
        }

        # Determine priority order
        if provider_order:
            self.provider_order = [p.strip().lower() for p in provider_order]
        else:
            raw_order = settings.llm_provider_order or "openai,groq,gemini,openrouter"
            self.provider_order = [p.strip().lower() for p in raw_order.split(",") if p.strip()]

        self._last_execution_metadata: Optional[Dict[str, Any]] = None

    def get_configured_providers(self) -> List[BaseLLMProvider]:
        """Returns list of providers in priority order that have valid API keys configured."""
        ordered = []
        for name in self.provider_order:
            if name in self.providers:
                p = self.providers[name]
                if p.is_configured():
                    ordered.append(p)
        return ordered

    def get_last_execution_metadata(self) -> Optional[Dict[str, Any]]:
        """Returns safe metadata dict from the last LLM execution for observability."""
        return self._last_execution_metadata

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        response_schema: Type[BaseModel],
        temperature: float = 0.0
    ) -> LLMResponse:
        """
        Executes structured generation across the provider failover chain.
        Attempts primary provider -> secondary -> tertiary -> final.
        If all providers fail, raises AllProvidersFailedException.
        """
        configured_providers = self.get_configured_providers()
        if not configured_providers:
            logger.warning("No LLM providers are configured with API keys in environment.")
            raise AllProvidersFailedException("No configured LLM providers available.")

        fallback_from: Optional[str] = None
        attempt_counter = 0

        for provider in configured_providers:
            p_name = provider.name

            # Check in-process health & cooldown state
            if not self.tracker.is_available(p_name):
                state = self.tracker.get_state(p_name)
                logger.info(
                    f"Skipping provider '{p_name}' (status={state.status}, cooldown_until={state.cooldown_until:.1f})."
                )
                continue

            attempt_counter += 1
            start_time = time.time()

            logger.info(
                f"Attempting LLM call #{attempt_counter} using provider '{p_name}' (model='{provider.model}')."
            )

            try:
                result_dict = provider.generate_structured(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    response_schema=response_schema,
                    temperature=temperature
                )
                latency_ms = (time.time() - start_time) * 1000.0

                # Mark success in health tracker
                self.tracker.record_success(p_name)

                llm_response = LLMResponse(
                    content="",
                    parsed_json=result_dict,
                    provider=p_name,
                    model=provider.model,
                    attempt=attempt_counter,
                    total_attempts=attempt_counter,
                    latency_ms=latency_ms,
                    fallback_from=fallback_from,
                    status="success"
                )
                self._last_execution_metadata = llm_response.to_metadata_dict()
                logger.info(
                    f"LLM call succeeded using '{p_name}' in {latency_ms:.1f}ms "
                    f"(attempts={attempt_counter}, fallback_from={fallback_from})."
                )
                return llm_response

            except Exception as exc:
                latency_ms = (time.time() - start_time) * 1000.0
                status_code = getattr(exc, "status_code", getattr(exc, "code", None))
                category = classify_exception(exc, http_status=status_code)

                # Record failure in health tracker
                self.tracker.record_failure(p_name, category, cooldown_seconds=self.cooldown_seconds)

                # Do NOT fail over on non-retryable programming/schema bugs
                if not is_retryable_error(category):
                    logger.error(
                        f"Non-retryable error in provider '{p_name}' [{category.value}]: {exc}. "
                        f"Aborting failover chain."
                    )
                    raise exc

                logger.warning(
                    f"Provider '{p_name}' failed with retryable error [{category.value}] in {latency_ms:.1f}ms. "
                    f"Failing over to next provider..."
                )
                fallback_from = p_name

        # All configured & available providers failed
        logger.error(f"All {attempt_counter} attempted LLM providers failed. Triggering safe fallback.")
        self._last_execution_metadata = {
            "provider": "none",
            "model": "none",
            "attempt": attempt_counter,
            "total_attempts": attempt_counter,
            "status": "failed",
            "error_category": "all_providers_failed",
            "fallback_from": fallback_from
        }
        raise AllProvidersFailedException(f"All {attempt_counter} attempted providers failed.")
