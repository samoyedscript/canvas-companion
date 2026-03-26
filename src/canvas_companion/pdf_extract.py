"""PDF text extraction and chunking for FTS indexing."""

from __future__ import annotations

import logging

import fitz  # pymupdf

logger = logging.getLogger(__name__)

CHUNK_SIZE = 4000  # characters per chunk (~1000 tokens)
CHUNK_OVERLAP = 400  # overlap between consecutive chunks


def extract_text(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF byte string."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return "\n\n".join(page.get_text() for page in doc)


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks for FTS indexing."""
    if not text.strip():
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks


def extract_and_chunk(pdf_bytes: bytes) -> list[str]:
    """Extract text from PDF and return chunks ready for FTS indexing."""
    text = extract_text(pdf_bytes)
    return chunk_text(text)
