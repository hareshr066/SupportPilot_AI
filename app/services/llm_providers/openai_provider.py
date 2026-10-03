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

logger = logging.getLogger("llm_providers.openai")


class OpenAIProvider(BaseLLMProvider):
    """
    Adapter for OpenAI LLM Services (e.g. gpt-4o-mini).
    Uses official openai SDK when available, falling back to urllib REST requests.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        key = api_key or settings.openai_api_key
        mdl = model or settings.openai_model
        super().__init__(name="openai", model=mdl, api_key=key)

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0
    ) -> str:
        if not self.is_configured():
            raise ValueError("OpenAI API key is not configured.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                messages=messages
            )
            return response.choices[0].message.content or ""
        except ImportError:
            return self._urllib_generate(messages, temperature, json_mode=False)["choices"][0]["message"]["content"]
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            category = classify_exception(exc, http_status=status_code)
            logger.warning(f"OpenAI generate failed [{category.value}]: sanitize_err={type(exc).__name__}")
            raise exc

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        response_schema: Type[BaseModel],
        temperature: float = 0.0
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise ValueError("OpenAI API key is not configured.")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        try:
            raw_content = None
            try:
                import openai
                client = openai.OpenAI(api_key=self.api_key)
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
                raise ValueError("OpenAI returned empty response body.")

            parsed = json.loads(raw_content)
            sanitized = sanitize_json_dict(parsed, response_schema)
            validated = response_schema.model_validate(sanitized)
            return validated.model_dump()

        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            category = classify_exception(exc, http_status=status_code)
            logger.warning(f"OpenAI structured generation failed [{category.value}]: {type(exc).__name__}")
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
            "Authorization": f"Bearer {self.api_key}"
        }
        data = {
            "model": self.model,
            "temperature": temperature,
            "messages": messages
        }
        if json_mode:
            data["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(data).encode("utf-8"),
            headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as http_err:
            cat = classify_exception(http_err, http_status=http_err.code)
            raise http_err
