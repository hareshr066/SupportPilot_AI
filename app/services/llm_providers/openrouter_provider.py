import json
import logging
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel
from config import settings
from app.services.llm_providers.base import (
    BaseLLMProvider,
    LLMErrorCategory,
    classify_exception,
    sanitize_json_dict,
)

logger = logging.getLogger("llm_providers.openrouter")


class OpenRouterProvider(BaseLLMProvider):
    """
    Adapter for OpenRouter Multi-Model Aggregator Service.
    Treats OpenRouter as an OpenAI-compatible API endpoint with custom routing capabilities.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        key = api_key or settings.openrouter_api_key
        mdl = model or settings.openrouter_model
        self.base_url = base_url or settings.openrouter_base_url
        super().__init__(name="openrouter", model=mdl, api_key=key)

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0
    ) -> str:
        if not self.is_configured():
            raise ValueError("OpenRouter API key is not configured.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            import openai
            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                default_headers={
                    "HTTP-Referer": "https://supportpilot.ai",
                    "X-Title": "SupportPilot"
                }
            )
            response = client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                messages=messages
            )
            return response.choices[0].message.content or ""
        except ImportError:
            res_dict = self._urllib_generate(messages, temperature, json_mode=False)
            return res_dict["choices"][0]["message"]["content"]
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            category = classify_exception(exc, http_status=status_code)
            logger.warning(f"OpenRouter generate failed [{category.value}]: {type(exc).__name__}")
            raise exc

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        response_schema: Type[BaseModel],
        temperature: float = 0.0
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise ValueError("OpenRouter API key is not configured.")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        try:
            raw_content = None
            try:
                import openai
                client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    default_headers={
                        "HTTP-Referer": "https://supportpilot.ai",
                        "X-Title": "SupportPilot"
                    }
                )
                response = client.chat.completions.create(
                    model=self.model,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    messages=messages
                )
                raw_content = response.choices[0].message.content
            except ImportError:
                res_dict = self._urllib_generate(messages, temperature, json_mode=True)
                raw_content = res_dict["choices"][0]["message"]["content"]

            if not raw_content:
                raise ValueError("OpenRouter returned empty response body.")

            parsed = json.loads(raw_content)
            sanitized = sanitize_json_dict(parsed, response_schema)
            validated = response_schema.model_validate(sanitized)
            return validated.model_dump()

        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            category = classify_exception(exc, http_status=status_code)
            logger.warning(f"OpenRouter structured generation failed [{category.value}]: {type(exc).__name__} - {exc}")
            raise exc

    def _urllib_generate(
        self,
        messages: list,
        temperature: float,
        json_mode: bool = False
    ) -> Dict[str, Any]:
        import urllib.request
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://supportpilot.ai",
            "X-Title": "SupportPilot"
        }
        data = {
            "model": self.model,
            "temperature": temperature,
            "messages": messages
        }
        if json_mode:
            data["response_format"] = {"type": "json_object"}

        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(data).encode("utf-8"),
            headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as http_err:
            cat = classify_exception(http_err, http_status=http_err.code)
            raise http_err
