"""Agentic study pack generation: generate and critique."""

from __future__ import annotations

import logging

from canvas_companion.gemini_service import GeminiService
from canvas_companion.models import PrepRequest, PrepType

logger = logging.getLogger(__name__)

_MAX_CONTEXT_CHARS = 50_000  # ~12k tokens


def _build_material_summary_prompt(request: PrepRequest, chunks: list[str]) -> str:
    """Build Gemini prompt for an 8-10 point material summary."""
    context_block = (
        "\n---\n".join(chunks) if chunks else "(No course materials found)"
    )

    return f"""You are a study assistant for an NUS university student.

Course: {request.course_name}
Material: {request.file_display_name}

TASK:
Generate a clear, readable summary of the provided material with 8-10 numbered points.

Formatting rules (strictly follow these):
- Start with <b>Summary — {request.file_display_name}</b> as the title
- Leave one blank line after the title
- Number each point: 1. 2. 3. etc.
- Each point is one concise sentence capturing a key idea
- Leave one blank line between every two points for readability
- End with a <b>Key Takeaways</b> section containing 2-3 bullet points (use •)
- Use <b>bold</b> ONLY for the title and "Key Takeaways" header
- Do NOT use <br> tags — use real newlines only
- No dense paragraphs

Ground your summary ONLY in the provided course materials. If something is not covered, omit it.

--- COURSE MATERIALS ---
{context_block}
--- END MATERIALS ---"""


def _build_quiz_prep_prompt(request: PrepRequest, chunks: list[str]) -> str:
    """Build Gemini prompt for quiz prep: summary + 5 mock questions."""
    context_block = (
        "\n---\n".join(chunks) if chunks else "(No course materials found)"
    )

    return f"""You are a study assistant for an NUS university student.

Course: {request.course_name}
Quiz: {request.quiz_name}
Material: {request.file_display_name}

TASK:
Generate a quiz preparation guide based on the provided material.

Structure:
1. A summary section with 8-10 numbered key points from the material
2. A mock questions section with exactly 5 questions and model answers

Formatting rules (strictly follow these):
- Start with <b>Quiz Prep — {request.quiz_name}</b> as the title
- Leave one blank line after the title
- Section header: <b>Summary</b> (blank line before and after)
- Number each summary point: 1. 2. 3. etc., one per line
- Section header: <b>Mock Questions</b> (blank line before and after)
- Format each question as:
  <b>Q1.</b> [question text]
  <b>A:</b> [concise model answer]
  (blank line between each Q&A pair)
- Use <b>bold</b> ONLY for the two section headers, "Q1."/"A:" labels, and the title
- Do NOT use <br> tags — use real newlines only
- No dense paragraphs

Ground all content ONLY in the provided course materials.

--- COURSE MATERIALS ---
{context_block}
--- END MATERIALS ---"""


def _build_critique_prompt(study_pack: str, chunks: list[str]) -> str:
    """Build a critique/validation prompt."""
    context_block = (
        "\n---\n".join(chunks) if chunks else "(No materials)"
    )

    return f"""You are a fact-checker for student study materials.

Review the following study pack and verify every claim against the provided course materials.

STUDY PACK:
{study_pack}

--- COURSE MATERIALS ---
{context_block}
--- END MATERIALS ---

For each factual claim in the study pack:
- If supported by the materials, keep it unchanged
- If NOT supported, remove it or mark it clearly as [unverified]

Output a revised version of the study pack that:
1. Keeps all verified content unchanged (including all HTML formatting tags)
2. Removes any fabricated content
3. Marks genuinely unverified claims with [unverified]

Output ONLY the revised study pack. No commentary."""


async def generate_study_pack(
    request: PrepRequest,
    chunks: list[str],
    gemini: GeminiService,
) -> str:
    """Generate and optionally critique a study pack from pre-fetched chunks."""
    # Trim chunks to stay within token budget
    trimmed: list[str] = []
    total = 0
    for chunk in chunks:
        if total + len(chunk) > _MAX_CONTEXT_CHARS:
            break
        trimmed.append(chunk)
        total += len(chunk)

    logger.info("Generating study pack with %d chunks (%d chars)", len(trimmed), total)

    if request.prep_type == PrepType.MATERIAL_SUMMARY:
        prompt = _build_material_summary_prompt(request, trimmed)
    else:
        prompt = _build_quiz_prep_prompt(request, trimmed)

    raw_pack = await gemini.generate(prompt)
    logger.info("Generated study pack (%d chars)", len(raw_pack))

    # Critique pass only when we have real content to validate against
    if trimmed:
        critique_prompt = _build_critique_prompt(raw_pack, trimmed)
        refined_pack = await gemini.generate(critique_prompt)
        logger.info("Critique pass complete (%d chars)", len(refined_pack))
        return refined_pack

    return raw_pack
