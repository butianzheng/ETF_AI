"""LLM 客户端封装。"""
from __future__ import annotations

import os
import time
from typing import Dict, List, Optional

from src.core.logger import get_logger

logger = get_logger(__name__)


class LLMClient:
    """统一封装 OpenAI / Anthropic 调用。"""

    def __init__(
        self,
        provider: str = "openai",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.provider = provider.lower()
        self.api_base = api_base
        self.timeout = timeout
        self.max_retries = max_retries
        env_var = "OPENAI_API_KEY" if self.provider == "openai" else "ANTHROPIC_API_KEY"
        self.api_key = api_key or os.getenv(env_var)
        self.client = None

        if not self.api_key:
            logger.warning(f"LLM API key not found for provider {self.provider}, fallback mode enabled")
            return

        if self.provider == "openai":
            from openai import OpenAI

            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_base,
                timeout=self.timeout,
            )
        elif self.provider == "anthropic":
            from anthropic import Anthropic

            self.client = Anthropic(api_key=self.api_key, base_url=self.api_base, timeout=self.timeout)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def is_available(self) -> bool:
        return self.client is not None

    def _call_openai(self, messages: List[Dict[str, str]], model: str, temperature: float, max_tokens: int) -> str:
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    def _call_anthropic(self, messages: List[Dict[str, str]], model: str, temperature: float, max_tokens: int) -> str:
        system_messages = [m["content"] for m in messages if m["role"] == "system"]
        user_messages = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system="\n".join(system_messages),
            messages=user_messages,
        )
        if isinstance(response.content, list) and response.content:
            return response.content[0].text.strip()
        return str(response.content).strip()

    def call(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o-mini",
        temperature: float = 0.5,
        max_tokens: int = 2000,
    ) -> str:
        if not self.is_available():
            raise RuntimeError("LLM client unavailable")

        for attempt in range(self.max_retries):
            try:
                if self.provider == "openai":
                    return self._call_openai(messages, model, temperature, max_tokens)
                return self._call_anthropic(messages, model, temperature, max_tokens)
            except Exception as exc:
                logger.warning(f"LLM call attempt {attempt + 1} failed: {exc}")
                if attempt + 1 == self.max_retries:
                    raise
                time.sleep(2 ** attempt)

        raise RuntimeError("LLM call failed unexpectedly")

    def __repr__(self) -> str:
        return f"LLMClient(provider={self.provider}, available={self.is_available()})"
