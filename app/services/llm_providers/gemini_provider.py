import json
import logging
import urllib.request
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel
from config import settings
from app.services.llm_providers.base import (
    BaseLLMProvider,
    LLMErrorCategory,
    classify_exception,
    sanitize_json_dict,
)

logger = logging.getLogger("llm_providers.gemini")


class GeminiProvider(BaseLLMProvider):
    """
    Adapter for Google Gemini AI Services (e.g. gemini-1.5-flash).
    Uses official Gemini REST API with json_mime_type generation mode.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        key = api_key or settings.gemini_api_key
        mdl = model or settings.gemini_model
        super().__init__(name="gemini", model=mdl, api_key=key)

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0
    ) -> str:
        if not self.is_configured():
            raise ValueError("Gemini API key is not configured.")

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\nUSER PROMPT:\n{prompt}"

        try:
            return self._call_gemini_api(full_prompt, temperature, json_mode=False)
        except Exception as exc:
            status_code = getattr(exc, "code", getattr(exc, "status_code", None))
            category = classify_exception(exc, http_status=status_code)
            logger.warning(f"Gemini generate failed [{category.value}]: {type(exc).__name__}")
            raise exc

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        response_schema: Type[BaseModel],
        temperature: float = 0.0
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise ValueError("Gemini API key is not configured.")

        full_prompt = (
            f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\n"
            f"CRITICAL: Return output strictly in valid JSON adhering to the required schema.\n\n"
            f"USER PROMPT:\n{prompt}"
        )

        try:
            raw_content = self._call_gemini_api(full_prompt, temperature, json_mode=True)
            if not raw_content:
                raise ValueError("Gemini returned empty text content.")

            # Extract JSON substring if Gemini added markdown ```json wrappers
            raw_clean = raw_content.strip()
            if raw_clean.startswith("```json"):
                raw_clean = raw_clean[7:]
            elif raw_clean.startswith("```"):
                raw_clean = raw_clean[3:]
            if raw_clean.endswith("```"):
                raw_clean = raw_clean[:-3]
            raw_clean = raw_clean.strip()

            parsed = json.loads(raw_clean)
            sanitized = sanitize_json_dict(parsed, response_schema)
            validated = response_schema.model_validate(sanitized)
            return validated.model_dump()

        except Exception as exc:
            status_code = getattr(exc, "code", getattr(exc, "status_code", None))
            category = classify_exception(exc, http_status=status_code)
            logger.warning(f"Gemini structured generation failed [{category.value}]: {type(exc).__name__}")
            raise exc

    def _call_gemini_api(
        self,
        prompt_text: str,
        temperature: float,
        json_mode: bool = False
    ) -> str:
        """Invokes Gemini REST API v1beta."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        
        gen_config = {"temperature": temperature}
        if json_mode:
            gen_config["response_mime_type"] = "application/json"

        body = {
            "contents": [
                {
                    "parts": [{"text": prompt_text}]
                }
            ],
            "generationConfig": gen_config
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                candidates = result.get("candidates", [])
                if not candidates:
                    raise ValueError("Gemini API response contained no candidates.")
                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    raise ValueError("Gemini candidate contained no parts.")
                return parts[0].get("text", "")
        except urllib.error.HTTPError as http_err:
            cat = classify_exception(http_err, http_status=http_err.code)
            raise http_err
