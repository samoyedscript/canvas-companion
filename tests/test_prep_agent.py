"""Tests for prep_agent.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from canvas_companion import db
from canvas_companion.models import PrepRequest, PrepType
from canvas_companion.prep_agent import (
    _build_critique_prompt,
    _build_material_summary_prompt,
    _build_quiz_prep_prompt,
    generate_study_pack,
)


def _make_request(**kwargs) -> PrepRequest:
    defaults = dict(
        course_id=101,
        course_name="CS101 Data Structures",
        course_code="CS101",
        prep_type=PrepType.MATERIAL_SUMMARY,
        file_display_name="Lecture 5.pdf",
    )
    defaults.update(kwargs)
    return PrepRequest(**defaults)


def test_build_material_summary_prompt_contains_key_fields():
    request = _make_request()
    prompt = _build_material_summary_prompt(request, ["Some content here"])
    assert "CS101 Data Structures" in prompt
    assert "Lecture 5.pdf" in prompt
    assert "8-10" in prompt
    assert "Some content here" in prompt


def test_build_material_summary_prompt_no_context():
    request = _make_request()
    prompt = _build_material_summary_prompt(request, [])
    assert "No course materials found" in prompt


def test_build_quiz_prep_prompt_contains_key_fields():
    request = _make_request(
        prep_type=PrepType.QUIZ_PREP,
        quiz_name="Quiz 3",
    )
    prompt = _build_quiz_prep_prompt(request, ["Some content here"])
    assert "CS101 Data Structures" in prompt
    assert "Quiz 3" in prompt
    assert "Lecture 5.pdf" in prompt
    assert "5 questions" in prompt.lower() or "Mock Questions" in prompt
    assert "Some content here" in prompt


def test_build_quiz_prep_prompt_no_context():
    request = _make_request(prep_type=PrepType.QUIZ_PREP, quiz_name="Quiz 1")
    prompt = _build_quiz_prep_prompt(request, [])
    assert "No course materials found" in prompt


def test_build_critique_prompt():
    prompt = _build_critique_prompt("Study pack text", ["Source chunk"])
    assert "Study pack text" in prompt
    assert "Source chunk" in prompt
    assert "fact-checker" in prompt.lower()


@pytest.mark.asyncio
async def test_generate_study_pack_material_summary_with_chunks():
    mock_gemini = MagicMock()
    mock_gemini.generate = AsyncMock(side_effect=[
        "Raw summary",
        "Refined summary",
    ])

    request = _make_request()
    result = await generate_study_pack(request, ["chunk1", "chunk2"], mock_gemini)
    assert result == "Refined summary"
    assert mock_gemini.generate.call_count == 2


@pytest.mark.asyncio
async def test_generate_study_pack_quiz_prep_with_chunks():
    mock_gemini = MagicMock()
    mock_gemini.generate = AsyncMock(side_effect=[
        "Raw quiz pack",
        "Refined quiz pack",
    ])

    request = _make_request(prep_type=PrepType.QUIZ_PREP, quiz_name="Quiz 2")
    result = await generate_study_pack(request, ["chunk1"], mock_gemini)
    assert result == "Refined quiz pack"
    assert mock_gemini.generate.call_count == 2


@pytest.mark.asyncio
async def test_generate_study_pack_no_chunks_skips_critique():
    """Without chunks, critique pass should be skipped."""
    mock_gemini = MagicMock()
    mock_gemini.generate = AsyncMock(return_value="Raw output only")

    request = _make_request()
    result = await generate_study_pack(request, [], mock_gemini)
    assert result == "Raw output only"
    assert mock_gemini.generate.call_count == 1


@pytest.mark.asyncio
async def test_generate_study_pack_routes_to_correct_prompt():
    """Material summary and quiz prep should call different prompt builders."""
    mock_gemini = MagicMock()
    mock_gemini.generate = AsyncMock(return_value="output")

    summary_request = _make_request(prep_type=PrepType.MATERIAL_SUMMARY)
    quiz_request = _make_request(prep_type=PrepType.QUIZ_PREP, quiz_name="Q1")

    with (
        __import__("unittest.mock", fromlist=["patch"]).patch(
            "canvas_companion.prep_agent._build_material_summary_prompt",
            return_value="summary_prompt",
        ) as mock_summary,
        __import__("unittest.mock", fromlist=["patch"]).patch(
            "canvas_companion.prep_agent._build_quiz_prep_prompt",
            return_value="quiz_prompt",
        ) as mock_quiz,
    ):
        await generate_study_pack(summary_request, [], mock_gemini)
        mock_summary.assert_called_once()
        mock_quiz.assert_not_called()

        mock_gemini.generate.reset_mock()
        mock_summary.reset_mock()

        await generate_study_pack(quiz_request, [], mock_gemini)
        mock_quiz.assert_called_once()
        mock_summary.assert_not_called()
