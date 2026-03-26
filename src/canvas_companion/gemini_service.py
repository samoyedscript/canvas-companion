"""Gemini API wrapper for study pack generation."""

from __future__ import annotations

import logging

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class GeminiService:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def generate(self, prompt: str, max_tokens: int = 8192) -> str:
        """Generate text from a prompt. Returns the response text."""
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=0.3,
            ),
        )
        return response.text or ""

    async def check_connectivity(self) -> bool:
        """Test that the API key works."""
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents="Reply with exactly: OK",
                config=types.GenerateContentConfig(max_output_tokens=5),
            )
            return bool(response.text and "OK" in response.text)
        except Exception as e:
            logger.warning("Gemini connectivity check failed: %s", e)
            return False
