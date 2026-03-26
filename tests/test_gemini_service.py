"""Tests for gemini_service.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from canvas_companion.gemini_service import GeminiService


@pytest.fixture
def gemini():
    """Create a GeminiService with a mocked client."""
    with patch("canvas_companion.gemini_service.genai") as mock_genai:
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        service = GeminiService(api_key="fake-key", model="gemini-2.5-flash")
        yield service, mock_client


@pytest.mark.asyncio
async def test_generate_calls_api(gemini):
    service, mock_client = gemini
    mock_response = MagicMock()
    mock_response.text = "Generated study pack content"
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    result = await service.generate("Test prompt")
    assert result == "Generated study pack content"
    mock_client.aio.models.generate_content.assert_called_once()


@pytest.mark.asyncio
async def test_generate_empty_response(gemini):
    service, mock_client = gemini
    mock_response = MagicMock()
    mock_response.text = None
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    result = await service.generate("Test prompt")
    assert result == ""


@pytest.mark.asyncio
async def test_check_connectivity_success(gemini):
    service, mock_client = gemini
    mock_response = MagicMock()
    mock_response.text = "OK"
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    assert await service.check_connectivity() is True


@pytest.mark.asyncio
async def test_check_connectivity_failure(gemini):
    service, mock_client = gemini
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=Exception("API error"),
    )

    assert await service.check_connectivity() is False
