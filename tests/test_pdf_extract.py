"""Tests for pdf_extract.py."""

from __future__ import annotations

import fitz  # pymupdf

from canvas_companion.pdf_extract import chunk_text, extract_and_chunk, extract_text


def _make_pdf(text: str) -> bytes:
    """Create a minimal PDF with the given text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_extract_text_from_pdf():
    pdf = _make_pdf("Hello, World!")
    text = extract_text(pdf)
    assert "Hello, World!" in text


def test_extract_text_empty_pdf():
    doc = fitz.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()
    text = extract_text(pdf_bytes)
    assert text.strip() == ""


def test_chunk_text_basic():
    text = "A" * 8000
    chunks = chunk_text(text, chunk_size=4000, overlap=400)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 4000


def test_chunk_text_overlap():
    text = "ABCDEFGHIJ" * 1000  # 10000 chars
    chunks = chunk_text(text, chunk_size=4000, overlap=400)
    assert len(chunks) >= 3
    # Verify overlap: end of chunk N should appear at start of chunk N+1
    for i in range(len(chunks) - 1):
        tail = chunks[i][-400:]
        assert tail in chunks[i + 1]


def test_chunk_text_small_input():
    text = "Short text"
    chunks = chunk_text(text, chunk_size=4000, overlap=400)
    assert len(chunks) == 1
    assert chunks[0] == "Short text"


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_extract_and_chunk_integration():
    pdf = _make_pdf("This is a test document for FTS indexing.")
    chunks = extract_and_chunk(pdf)
    assert len(chunks) >= 1
    assert "test document" in chunks[0]
