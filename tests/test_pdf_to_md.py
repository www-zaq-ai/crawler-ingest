"""
Tests for pdf_to_md.py — focusing on pure functions and the chunk page_num
resolution fix (KeyError 'page' across pymupdf4llm versions).
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

import pdf_to_md
from pdf_to_md import classify_page, strip_text_keep_images


# ---------------------------------------------------------------------------
# classify_page
# ---------------------------------------------------------------------------

class TestClassifyPage:
    def test_text_heavy_no_images(self):
        text = "This is a paragraph with enough words to be considered text heavy content here."
        page_type, word_count = classify_page(text)
        assert page_type == "text_heavy"
        assert word_count > 0

    def test_image_heavy_few_words(self):
        text = "![fig](image.png)\nCaption"
        page_type, word_count = classify_page(text, threshold=30)
        assert page_type == "image_heavy"

    def test_image_heavy_threshold_boundary(self):
        # Exactly at threshold with an image → text_heavy (word_count not < threshold)
        words = " ".join(["word"] * 30)
        text = f"![fig](img.png)\n{words}"
        page_type, _ = classify_page(text, threshold=30)
        assert page_type == "text_heavy"

    def test_no_images_always_text_heavy(self):
        text = "just a few words"
        page_type, _ = classify_page(text)
        assert page_type == "text_heavy"

    def test_word_count_excludes_single_chars(self):
        text = "a b c I x word"
        _, word_count = classify_page(text)
        assert word_count == 1  # only 'word' qualifies (len >= 2)


# ---------------------------------------------------------------------------
# strip_text_keep_images
# ---------------------------------------------------------------------------

class TestStripTextKeepImages:
    def test_keeps_image_lines(self):
        text = "Some text\n![alt](image.png)\nMore text"
        result = strip_text_keep_images(text)
        assert "![alt](image.png)" in result
        assert "Some text" not in result
        assert "More text" not in result

    def test_multiple_images(self):
        text = "intro\n![a](a.png)\nmiddle\n![b](b.png)\nend"
        result = strip_text_keep_images(text)
        lines = result.strip().split("\n")
        assert lines == ["![a](a.png)", "![b](b.png)"]

    def test_no_images_returns_empty(self):
        text = "only text here, no images"
        result = strip_text_keep_images(text)
        assert result == ""


# ---------------------------------------------------------------------------
# Chunk page_num resolution (the bug fix)
# ---------------------------------------------------------------------------

def _make_fitz_doc_mock():
    """Return a mock fitz document that reconstruct_page_tables handles safely."""
    page_mock = MagicMock()
    page_mock.get_text.return_value = {"blocks": []}
    doc_mock = MagicMock()
    doc_mock.__iter__ = MagicMock(return_value=iter([]))
    doc_mock.__len__ = MagicMock(return_value=1)
    return doc_mock


def _run_pdf_to_markdown_with_chunks(chunks):
    """
    Call pdf_to_markdown with mocked pymupdf4llm and fitz, injecting the
    given chunks. Returns the written markdown string.
    """
    written = []

    def fake_write_bytes(self, data):
        written.append(data.decode() if isinstance(data, bytes) else data)

    doc_mock = _make_fitz_doc_mock()

    with patch("pdf_to_md.pymupdf4llm.to_markdown", return_value=chunks), \
         patch("pdf_to_md.fitz.open", return_value=doc_mock), \
         patch("pdf_to_md.get_image_overlap_text", return_value={}), \
         patch("pdf_to_md.reconstruct_page_tables", return_value={}), \
         patch.object(Path, "write_bytes", fake_write_bytes), \
         patch.object(Path, "exists", return_value=True), \
         patch.object(Path, "mkdir", return_value=None):

        pdf_to_md.pdf_to_markdown(
            "/fake/input.pdf",
            "/fake/output.md",
            write_images=False,
        )

    return "".join(written)


class TestChunkPageResolution:
    """Verify page_num is extracted correctly from both pymupdf4llm chunk formats."""

    def test_old_format_metadata_page(self):
        """pymupdf4llm <0.0.17: page number lives in chunk['metadata']['page'] (1-indexed)."""
        chunks = [
            {"metadata": {"page": 1}, "text": "Page one content with enough words here yes"},
            {"metadata": {"page": 2}, "text": "Page two content with enough words here yes"},
        ]
        md = _run_pdf_to_markdown_with_chunks(chunks)
        assert "<!-- page: 1 -->" in md
        assert "<!-- page: 2 -->" in md

    def test_new_format_top_level_page(self):
        """pymupdf4llm >=0.0.17: page number is top-level chunk['page'] (0-indexed)."""
        chunks = [
            {"metadata": {}, "page": 0, "text": "Page one content with enough words here yes"},
            {"metadata": {}, "page": 1, "text": "Page two content with enough words here yes"},
        ]
        md = _run_pdf_to_markdown_with_chunks(chunks)
        assert "<!-- page: 1 -->" in md
        assert "<!-- page: 2 -->" in md

    def test_missing_page_key_falls_back_to_index(self):
        """If neither metadata.page nor chunk.page exist, fall back to enumeration index."""
        chunks = [
            {"metadata": {}, "text": "First page content with enough words here yes"},
            {"metadata": {}, "text": "Second page content with enough words here yes"},
        ]
        md = _run_pdf_to_markdown_with_chunks(chunks)
        assert "<!-- page: 1 -->" in md
        assert "<!-- page: 2 -->" in md

    def test_old_format_does_not_raise_key_error(self):
        """Regression: the original KeyError: 'page' must not occur."""
        chunks = [{"metadata": {"file_path": "/fake/input.pdf"}, "text": "hello world content here"}]
        # Should not raise
        _run_pdf_to_markdown_with_chunks(chunks)
