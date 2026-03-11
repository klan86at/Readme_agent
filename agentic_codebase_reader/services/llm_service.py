"""
services/llm_service.py
~~~~~~~~~~~~~~~~~~~~~~~
LLM client abstraction — Google Gemini and OpenAI backends with retry.
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agentic_codebase_reader.config import settings

logger = logging.getLogger(__name__)
MAX_RETRIES = 3


@runtime_checkable
class LLMClient(Protocol):
    """Duck-typing protocol — both concrete clients must satisfy this."""

    async def complete(self, prompt: str, *, max_tokens: int = 2048) -> str:
        """Send a prompt and return the model's text response."""
        ...


# ── Google Gemini ─────────────────────────────────────────────────────────────

class GeminiClient:
    """Google Gemini LLM client (google-genai SDK)."""

    def __init__(self, model: str | None = None) -> None:
        self.model_name = model or settings.google_model
        self._client: object | None = None

    def _get_client(self) -> object:
        if self._client is None:
            from google import genai  # type: ignore[import]
            self._client = genai.Client(api_key=settings.google_api_key)
        return self._client

    # ── Standard generation ───────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def complete(self, prompt: str, *, max_tokens: int = 2048) -> str:
        """Send a prompt to Gemini and return the text response."""
        import asyncio
        client = self._get_client()

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(  # type: ignore[attr-defined]
                model=self.model_name,
                contents=prompt,
            ),
        )
        text = response.text
        if not text:
            logger.warning("Gemini returned empty response (possibly safety-blocked).")
            return ""
        return text

    # ── Context caching ───────────────────────────────────────────────────────

    def create_context_cache(
        self,
        context: str,
        ttl_seconds: int = 3600,
    ) -> str | None:
        """Upload a context string to Gemini's server-side cache.

        Args:
            context:     The text to cache (repository context, file tree, etc.).
            ttl_seconds: Cache time-to-live in seconds (default 1 hour).

        Returns:
            The opaque ``cache_name`` string to pass to subsequent calls,
            or ``None`` if caching is unavailable / context is too small.
        """
        try:
            from google import genai  # type: ignore[import]
            from google.genai import types  # type: ignore[import]

            client = self._get_client()
            cache_config = types.CreateCachedContentConfig(
                ttl=f"{ttl_seconds}s",
                system_instruction=context,
            )
            cached = client.caches.create(  # type: ignore[attr-defined]
                model=self.model_name,
                config=cache_config,
            )
            logger.info("Context cache created: %s", cached.name)
            return cached.name
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Context cache creation failed (will use uncached generation): %s", exc
            )
            return None

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def complete_with_cache(
        self,
        cache_name: str,
        prompt: str,
        *,
        max_tokens: int = 2048,
    ) -> str:
        """Generate content referencing a server-side context cache.

        Args:
            cache_name: The opaque name returned by :meth:`create_context_cache`.
            prompt:     The user-visible prompt (added on top of cached context).
            max_tokens: Maximum output tokens.

        Returns:
            The model's text response.
        """
        import asyncio
        from google.genai import types  # type: ignore[import]

        client = self._get_client()
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(  # type: ignore[attr-defined]
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    cached_content=cache_name,
                ),
            ),
        )
        text = response.text
        if not text:
            logger.warning("Gemini cached response returned empty text.")
            return ""
        return text

    def delete_context_cache(self, cache_name: str) -> None:
        """Delete a server-side context cache.

        Args:
            cache_name: The name returned by :meth:`create_context_cache`.
        """
        try:
            client = self._get_client()
            client.caches.delete(name=cache_name)  # type: ignore[attr-defined]
            logger.info("Context cache deleted: %s", cache_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete context cache %s: %s", cache_name, exc)


# ── OpenAI ────────────────────────────────────────────────────────────────────

class OpenAIClient:
    """OpenAI LLM client (openai >= 1.x)."""

    def __init__(self, model: str | None = None) -> None:
        self.model_name = model or settings.openai_model
        self._client: object | None = None

    def _get_client(self) -> object:
        if self._client is None:
            from openai import AsyncOpenAI  # type: ignore[import]
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def complete(self, prompt: str, *, max_tokens: int = 2048) -> str:
        """Send a prompt to OpenAI and return the text response."""
        client = self._get_client()
        response = await client.chat.completions.create(  # type: ignore[attr-defined]
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""


# ── Factory ───────────────────────────────────────────────────────────────────

def get_llm_client() -> LLMClient:
    """Return the configured LLM client based on ``settings.llm_provider``.

    Returns:
        A :class:`GeminiClient` or :class:`OpenAIClient`.

    Raises:
        ValueError: If the configured provider is unsupported.
    """
    provider = settings.llm_provider.lower()
    if provider == "google":
        logger.debug("Using Gemini LLM client (%s)", settings.google_model)
        return GeminiClient()
    if provider == "openai":
        logger.debug("Using OpenAI LLM client (%s)", settings.openai_model)
        return OpenAIClient()
    raise ValueError(
        f"Unsupported LLM provider {provider!r}. "
        "Set LLM_PROVIDER=google or LLM_PROVIDER=openai in .env"
    )
