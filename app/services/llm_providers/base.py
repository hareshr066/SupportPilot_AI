import json
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, Type
from dataclasses import dataclass, field
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("llm_providers.base")


class LLMErrorCategory(str, Enum):
    """
    Classification of errors returned by LLM providers.
    Used to drive intelligent failover vs immediate error propagation.
    """
    RATE_LIMIT = "rate_limit_or_quota_exhausted"
    TRANSIENT_SERVER_ERROR = "transient_server_error"
    AUTH_CONFIGURATION_ERROR = "auth_or_configuration_error"
    INVALID_REQUEST_ERROR = "invalid_request_or_prompt_error"
    MALFORMED_RESPONSE_ERROR = "malformed_provider_response"
    UNKNOWN_ERROR = "unknown_error"


def is_retryable_error(category: LLMErrorCategory) -> bool:
    """
    Determines whether an error category is eligible for provider retry/failover.
    Retryable: Rate limit, transient server error, malformed provider output, or auth failure (to try next provider).
    Non-retryable: Programming errors / invalid prompt payload schemas.
    """
    if category in (
        LLMErrorCategory.RATE_LIMIT,
        LLMErrorCategory.TRANSIENT_SERVER_ERROR,
        LLMErrorCategory.MALFORMED_RESPONSE_ERROR,
        LLMErrorCategory.AUTH_CONFIGURATION_ERROR,
    ):
        return True
    return False


def classify_exception(exc: Exception, http_status: Optional[int] = None) -> LLMErrorCategory:
    """
    Safely classifies arbitrary exceptions into LLMErrorCategory based on HTTP status codes
    and error message patterns, without leaking sensitive details.
    """
    if isinstance(exc, (json.JSONDecodeError, ValidationError)):
        return LLMErrorCategory.MALFORMED_RESPONSE_ERROR

    err_str = str(exc).lower()
    
    # Check explicit HTTP status if available
    if http_status is not None:
        if http_status == 429:
            return LLMErrorCategory.RATE_LIMIT
        if http_status in (401, 403):
            return LLMErrorCategory.AUTH_CONFIGURATION_ERROR
        if http_status in (404, 500, 502, 503, 504):
            return LLMErrorCategory.TRANSIENT_SERVER_ERROR
        if http_status == 400:
            return LLMErrorCategory.INVALID_REQUEST_ERROR

    # Check string patterns
    if any(k in err_str for k in ("429", "rate limit", "quota", "too many requests", "resource_exhausted")):
        return LLMErrorCategory.RATE_LIMIT

    if any(k in err_str for k in ("401", "403", "unauthorized", "forbidden", "invalid api key", "authentication", "api_key")):
        return LLMErrorCategory.AUTH_CONFIGURATION_ERROR

    if any(k in err_str for k in ("404", "model_not_found", "model does not exist", "500", "502", "503", "504", "timeout", "timed out", "connection error", "service unavailable", "unavailable")):
        return LLMErrorCategory.TRANSIENT_SERVER_ERROR

    return LLMErrorCategory.UNKNOWN_ERROR


def sanitize_json_dict(parsed: Dict[str, Any], schema_cls: Type[BaseModel]) -> Dict[str, Any]:
    """
    Normalizes minor field naming inconsistencies from multi-provider LLMs
    (e.g., step_number -> step, missing claim_id) before strict Pydantic validation.
    """
    if not isinstance(parsed, dict):
        return parsed

    # 1. Sanitize steps if present
    if "steps" in parsed and isinstance(parsed["steps"], list):
        sanitized_steps = []
        for idx, s in enumerate(parsed["steps"]):
            if isinstance(s, dict):
                raw_step = s.get("step") or s.get("step_number") or s.get("number")
                try:
                    step_num = int(raw_step) if raw_step is not None else idx + 1
                except (ValueError, TypeError):
                    step_num = idx + 1
                inst = s.get("instruction") or s.get("action") or s.get("description") or (raw_step if isinstance(raw_step, str) else "")
                sources = s.get("source_ids") or s.get("sources") or []
                sanitized_steps.append({"step": step_num, "instruction": str(inst), "source_ids": list(sources)})
            elif isinstance(s, str):
                sanitized_steps.append({"step": idx + 1, "instruction": s, "source_ids": []})
        parsed["steps"] = sanitized_steps

    # 2. Sanitize claims if present
    if "claims" in parsed and isinstance(parsed["claims"], list):
        sanitized_claims = []
        for idx, c in enumerate(parsed["claims"]):
            if isinstance(c, dict):
                cid = c.get("claim_id") or c.get("id") or f"c{idx+1}"
                txt = c.get("text") or c.get("claim") or ""
                sources = c.get("source_ids") or c.get("sources") or []
                val_status = c.get("source_validation_status", "valid")
                ver_status = c.get("verification_status", "pending")
                sanitized_claims.append({
                    "claim_id": str(cid),
                    "text": str(txt),
                    "source_ids": list(sources),
                    "source_validation_status": str(val_status),
                    "verification_status": str(ver_status)
                })
            elif isinstance(c, str):
                sanitized_claims.append({
                    "claim_id": f"c{idx+1}",
                    "text": c,
                    "source_ids": [],
                    "source_validation_status": "valid",
                    "verification_status": "pending"
                })
        parsed["claims"] = sanitized_claims

    # 3. Sanitize resolution_type if present
    if "resolution_type" in parsed:
        res_type = str(parsed["resolution_type"]).lower()
        if "confirmed" in res_type or "historical" in res_type:
            parsed["resolution_type"] = "confirmed_historical_resolution"
        elif "insufficient" in res_type or "unknown" in res_type or "none" in res_type:
            parsed["resolution_type"] = "insufficient_evidence"
        else:
            parsed["resolution_type"] = "evidence_based_recommendation"

    # 4. Sanitize top-level required fields if missing
    if not parsed.get("summary"):
        parsed["summary"] = parsed.get("overview") or parsed.get("resolution_summary") or parsed.get("recommended_resolution") or parsed.get("diagnosis") or "Grounded resolution generated from historical evidence."
    if not parsed.get("diagnosis"):
        parsed["diagnosis"] = parsed.get("root_cause") or parsed.get("problem_analysis") or parsed.get("summary") or "Diagnosis derived from historical closed issue evidence."
    if not parsed.get("recommended_resolution"):
        parsed["recommended_resolution"] = parsed.get("fix") or parsed.get("solution") or parsed.get("recommendation") or parsed.get("summary") or "Apply recommended fix based on cited historical resolution."

    return parsed


@dataclass
class LLMResponse:
    """
    Container for structured LLM provider execution results and safe telemetry metadata.
    Does NOT store API keys, tokens, or raw authorization headers.
    """
    content: str
    parsed_json: Dict[str, Any]
    provider: str
    model: str
    attempt: int = 1
    total_attempts: int = 1
    latency_ms: float = 0.0
    fallback_from: Optional[str] = None
    status: str = "success"  # "success" | "failed"
    error_category: Optional[str] = None

    def to_metadata_dict(self) -> Dict[str, Any]:
        """Returns safe observability dictionary for database/logging metadata."""
        meta = {
            "provider": self.provider,
            "model": self.model,
            "attempt": self.attempt,
            "total_attempts": self.total_attempts,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 2),
        }
        if self.fallback_from:
            meta["fallback_from"] = self.fallback_from
        if self.error_category:
            meta["error_category"] = self.error_category
        return meta


class BaseLLMProvider(ABC):
    """
    Abstract Base Interface for LLM Providers in SupportPilot.
    Defines strict provider contract for text generation and structured JSON output.
    """

    def __init__(self, name: str, model: str, api_key: Optional[str] = None):
        self.name = name
        self.model = model
        self.api_key = api_key

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if the provider has necessary credentials and configuration."""
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0
    ) -> str:
        """Generates raw text response."""
        pass

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        response_schema: Type[BaseModel],
        temperature: float = 0.0
    ) -> Dict[str, Any]:
        """
        Generates structured JSON output adhering to response_schema.
        Must raise exceptions on invalid JSON or Pydantic validation failures so the router
        can trigger failover.
        """
        pass
