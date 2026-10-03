"""
Multi-Provider LLM Abstraction and Automatic Failover Package for SupportPilot.
"""
from app.services.llm_providers.base import (
    BaseLLMProvider,
    LLMResponse,
    LLMErrorCategory,
    classify_exception,
    is_retryable_error,
)
from app.services.llm_providers.health_tracker import (
    ProviderHealthTracker,
    ProviderState,
)
from app.services.llm_providers.openai_provider import OpenAIProvider
from app.services.llm_providers.groq_provider import GroqProvider
from app.services.llm_providers.gemini_provider import GeminiProvider
from app.services.llm_providers.openrouter_provider import OpenRouterProvider
from app.services.llm_providers.router import LLMProviderRouter

__all__ = [
    "BaseLLMProvider",
    "LLMResponse",
    "LLMErrorCategory",
    "classify_exception",
    "is_retryable_error",
    "ProviderHealthTracker",
    "ProviderState",
    "OpenAIProvider",
    "GroqProvider",
    "GeminiProvider",
    "OpenRouterProvider",
    "LLMProviderRouter",
]
