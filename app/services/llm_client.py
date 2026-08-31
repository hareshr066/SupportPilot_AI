import os
import json
import time
import logging
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel
from config import settings

logger = logging.getLogger("llm_client")


class LLMClient:
    """
    LLM Client Provider Abstraction supporting structured JSON generation,
    retry behavior with exponential backoff, and graceful fallback handling.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        max_retries: Optional[int] = None,
        temperature: Optional[float] = None
    ):
        self.model_name = model_name or settings.resolution_llm_model
        self.api_key = api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY")
        self.max_retries = max_retries or settings.resolution_max_retries
        self.temperature = temperature if temperature is not None else settings.resolution_temperature
        self._mock_response: Optional[Dict[str, Any]] = None

    def set_mock_response(self, mock_response: Dict[str, Any]):
        """Allows injecting mock LLM responses for unit testing without external API calls."""
        self._mock_response = mock_response

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        response_schema: Type[BaseModel]
    ) -> Dict[str, Any]:
        """
        Generates structured JSON adhering to response_schema.
        Retries up to max_retries with backoff.
        Returns parsed dict or fallback dict on failure.
        """
        # If mock response is injected, validate and return immediately
        if self._mock_response is not None:
            logger.info("Using mock LLM response for test execution.")
            try:
                validated = response_schema.model_validate(self._mock_response)
                return validated.model_dump()
            except Exception as e:
                logger.error(f"Mock response failed schema validation: {e}")
                return self._build_fallback_response()

        if not self.api_key:
            logger.warning("No OpenAI API Key found. Returning safe fallback structured response.")
            return self._build_fallback_response()

        attempt = 0
        backoff = 1.0

        while attempt < self.max_retries:
            attempt += 1
            try:
                # Attempt call using OpenAI / HTTP request
                result_dict = self._call_openai_api(prompt, system_prompt)
                validated = response_schema.model_validate(result_dict)
                return validated.model_dump()

            except Exception as exc:
                logger.warning(
                    f"LLM generation attempt {attempt}/{self.max_retries} failed: {exc}. "
                    f"Retrying in {backoff:.1f}s..."
                )
                time.sleep(backoff)
                backoff *= 2.0

        logger.error(f"All {self.max_retries} LLM attempts failed. Returning safe fallback response.")
        return self._build_fallback_response()

    def _call_openai_api(self, prompt: str, system_prompt: str) -> Dict[str, Any]:
        """Internal call to OpenAI Chat Completion API."""
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model_name,
                temperature=self.temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except ImportError:
            # Fallback using standard urllib / requests if openai module not installed
            import urllib.request
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            data = {
                "model": self.model_name,
                "temperature": self.temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            }
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(data).encode("utf-8"),
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
                return json.loads(content)

    def _build_fallback_response(self) -> Dict[str, Any]:
        """Safe fallback output when LLM is unavailable or fails schema validation."""
        return {
            "summary": "Insufficient historical resolution evidence available to synthesize a confident fix.",
            "diagnosis": "Unable to determine exact root cause from available evidence.",
            "recommended_resolution": "Manual support triage required. No reliable automated resolution established.",
            "resolution_type": "insufficient_evidence",
            "steps": [
                {
                    "step": 1,
                    "instruction": "Review ticket details and assign to technical support engineer.",
                    "source_ids": []
                }
            ],
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "Automated resolution evidence was insufficient for safe automated fix.",
                    "source_ids": [],
                    "source_validation_status": "valid",
                    "verification_status": "pending"
                }
            ],
            "limitations": [
                "No strong historical resolved cases found in retrieved context."
            ],
            "needs_human_review": True,
            "citation_coverage": 0.0,
            "unsupported_claim_rate": 0.0
        }
