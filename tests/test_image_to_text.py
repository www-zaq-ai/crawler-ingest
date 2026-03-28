"""Unit tests for image_to_text.py"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from image_to_text import PixtralImageProcessor, DESCRIBE_PROMPT, TRANSCRIBE_PROMPT


def _make_processor():
    """Return a PixtralImageProcessor with a mocked LLM — no real API key needed."""
    with patch("image_to_text.ChatOpenAI"):
        return PixtralImageProcessor(api_key="fake-key")


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestPixtralInit:
    def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("SCALEWAY_API_KEY", raising=False)
        with pytest.raises(ValueError, match="API key required"):
            PixtralImageProcessor()

    def test_accepts_explicit_api_key(self):
        with patch("image_to_text.ChatOpenAI") as mock_llm:
            p = PixtralImageProcessor(api_key="test-key")
            assert p.llm is mock_llm.return_value


# ---------------------------------------------------------------------------
# clean_description
# ---------------------------------------------------------------------------

class TestCleanDescription:
    def setup_method(self):
        self.p = _make_processor()

    def test_removes_certainly(self):
        assert "Certainly" not in self.p.clean_description("Certainly! Here is the info.")

    def test_removes_image_shows(self):
        result = self.p.clean_description("The image shows a chart with data.")
        assert "The image shows" not in result

    def test_strips_simple_bullets(self):
        result = self.p.clean_description("- First item\n- Second item")
        assert result == "First item\nSecond item"

    def test_keeps_structured_bullets(self):
        result = self.p.clean_description("- **Field:** Value")
        assert "- **Field:** Value" in result

    def test_collapses_excess_newlines(self):
        result = self.p.clean_description("Line one\n\n\n\nLine two")
        assert "\n\n\n" not in result

    def test_empty_string_returns_empty(self):
        assert self.p.clean_description("") == ""

    def test_removes_fluff_headline(self):
        result = self.p.clean_description("### Main Content:\nActual content here.")
        assert "### Main Content:" not in result
        assert "Actual content here." in result


# ---------------------------------------------------------------------------
# _load_image_heavy_set
# ---------------------------------------------------------------------------

class TestLoadImageHeavySet:
    def setup_method(self):
        self.p = _make_processor()

    def test_returns_empty_when_no_path(self):
        assert self.p._load_image_heavy_set(None) == set()

    def test_returns_empty_when_file_missing(self, tmp_path):
        result = self.p._load_image_heavy_set(str(tmp_path / "nonexistent.json"))
        assert result == set()

    def test_extracts_image_heavy_images(self, tmp_path):
        classification = {
            "1": {"type": "image_heavy", "images": ["fig1.png", "fig2.png"]},
            "2": {"type": "text_heavy", "images": ["fig3.png"]},
        }
        f = tmp_path / "classification.json"
        f.write_text(json.dumps(classification))
        result = self.p._load_image_heavy_set(str(f))
        assert result == {"fig1.png", "fig2.png"}

    def test_text_heavy_pages_excluded(self, tmp_path):
        classification = {"1": {"type": "text_heavy", "images": ["fig1.png"]}}
        f = tmp_path / "classification.json"
        f.write_text(json.dumps(classification))
        assert self.p._load_image_heavy_set(str(f)) == set()

    def test_multiple_image_heavy_pages_merged(self, tmp_path):
        classification = {
            "1": {"type": "image_heavy", "images": ["a.png"]},
            "2": {"type": "image_heavy", "images": ["b.png"]},
        }
        f = tmp_path / "classification.json"
        f.write_text(json.dumps(classification))
        result = self.p._load_image_heavy_set(str(f))
        assert result == {"a.png", "b.png"}


# ---------------------------------------------------------------------------
# get_image_description
# ---------------------------------------------------------------------------

class TestGetImageDescription:
    def setup_method(self):
        self.p = _make_processor()

    def test_raises_for_missing_image(self):
        with pytest.raises(FileNotFoundError):
            self.p.get_image_description("/nonexistent/image.png")

    def test_returns_cleaned_description(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fakeimage")

        mock_response = MagicMock()
        mock_response.content = "Certainly! A chart."
        self.p.llm.invoke = MagicMock(return_value=mock_response)

        result = self.p.get_image_description(str(img))
        assert "Certainly" not in result
        assert "chart" in result.lower()

    def test_uses_describe_prompt_by_default(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fakeimage")

        mock_response = MagicMock()
        mock_response.content = "A diagram."
        self.p.llm.invoke = MagicMock(return_value=mock_response)

        self.p.get_image_description(str(img))
        messages = self.p.llm.invoke.call_args[0][0]
        assert DESCRIBE_PROMPT in messages[0].content[0]["text"]

    def test_custom_prompt_overrides_default(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fakeimage")

        mock_response = MagicMock()
        mock_response.content = "Result."
        self.p.llm.invoke = MagicMock(return_value=mock_response)

        custom = "Extract all numbers."
        self.p.get_image_description(str(img), prompt=custom)
        messages = self.p.llm.invoke.call_args[0][0]
        assert custom in messages[0].content[0]["text"]

    def test_clean_false_skips_postprocessing(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fakeimage")

        mock_response = MagicMock()
        mock_response.content = "Certainly! Raw output."
        self.p.llm.invoke = MagicMock(return_value=mock_response)

        result = self.p.get_image_description(str(img), clean=False)
        assert "Certainly" in result
