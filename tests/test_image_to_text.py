"""Unit tests for image_to_text.py"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from image_to_text import PixtralImageProcessor, DESCRIBE_PROMPT, TRANSCRIBE_PROMPT, main
from langchain_core.messages import HumanMessage, SystemMessage


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

    def test_log_includes_model_name(self, tmp_path, capsys):
        img = tmp_path / "test.png"
        img.write_bytes(b"fakeimage")

        mock_response = MagicMock()
        mock_response.content = "A chart."
        self.p.llm.invoke = MagicMock(return_value=mock_response)
        self.p.llm.model_name = "gpt-4o"

        self.p.get_image_description(str(img))
        assert "gpt-4o" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# System prompt — processor-level behavior
# ---------------------------------------------------------------------------

class TestSystemPromptInjection:
    def test_system_prompt_none_by_default(self):
        p = _make_processor()
        assert p.system_prompt is None

    def test_system_prompt_stored_on_init(self):
        with patch("image_to_text.ChatOpenAI"):
            p = PixtralImageProcessor(api_key="fake", system_prompt="Be concise.")
        assert p.system_prompt == "Be concise."

    def test_system_message_prepended_when_set(self, tmp_path):
        with patch("image_to_text.ChatOpenAI"):
            p = PixtralImageProcessor(api_key="fake", system_prompt="Be concise.")
        img = tmp_path / "test.png"
        img.write_bytes(b"fakeimage")
        p.llm.invoke = MagicMock(return_value=MagicMock(content="A chart."))

        p.get_image_description(str(img))

        messages = p.llm.invoke.call_args[0][0]
        assert len(messages) == 2
        assert isinstance(messages[0], SystemMessage)
        assert messages[0].content == "Be concise."
        assert isinstance(messages[1], HumanMessage)

    def test_no_system_message_without_prompt(self, tmp_path):
        p = _make_processor()
        img = tmp_path / "test.png"
        img.write_bytes(b"fakeimage")
        p.llm.invoke = MagicMock(return_value=MagicMock(content="A chart."))

        p.get_image_description(str(img))

        messages = p.llm.invoke.call_args[0][0]
        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)

    def test_default_describe_prompt_used_when_no_system_prompt(self, tmp_path):
        p = _make_processor()
        img = tmp_path / "test.png"
        img.write_bytes(b"fakeimage")
        p.llm.invoke = MagicMock(return_value=MagicMock(content="A chart."))

        p.get_image_description(str(img))

        messages = p.llm.invoke.call_args[0][0]
        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)
        assert DESCRIBE_PROMPT in messages[0].content[0]["text"]

    def test_system_prompt_multiline(self, tmp_path):
        multiline = "Line one.\nLine two.\nLine three."
        with patch("image_to_text.ChatOpenAI"):
            p = PixtralImageProcessor(api_key="fake", system_prompt=multiline)
        img = tmp_path / "test.png"
        img.write_bytes(b"fakeimage")
        p.llm.invoke = MagicMock(return_value=MagicMock(content="Result."))

        p.get_image_description(str(img))

        messages = p.llm.invoke.call_args[0][0]
        assert messages[0].content == multiline


# ---------------------------------------------------------------------------
# System prompt — CLI resolution priority
# ---------------------------------------------------------------------------

class TestCliSystemPromptResolution:
    """Verifies that the correct system_prompt value reaches PixtralImageProcessor."""

    def _run_main(self, argv, tmp_path, monkeypatch=None, stdin_data=None):
        """
        Run main() with a real single-image arg and a mocked processor.
        Returns the system_prompt kwarg that was passed to PixtralImageProcessor().
        """
        img = tmp_path / "test.png"
        img.write_bytes(b"x")
        full_argv = ["prog", str(img)] + argv

        with patch("image_to_text.PixtralImageProcessor") as MockClass:
            mock_instance = MagicMock()
            mock_instance.get_image_description.return_value = "desc"
            MockClass.return_value = mock_instance

            with patch("sys.argv", full_argv):
                if stdin_data is not None:
                    with patch("sys.stdin") as mock_stdin:
                        mock_stdin.read.return_value = stdin_data
                        main()
                else:
                    main()

        return MockClass.call_args.kwargs.get("system_prompt")

    def test_inline_arg(self, tmp_path):
        result = self._run_main(["--system-prompt", "Be precise."], tmp_path)
        assert result == "Be precise."

    def test_file_arg(self, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("From file.")
        result = self._run_main(["--system-prompt-file", str(prompt_file)], tmp_path)
        assert result == "From file."

    def test_file_strips_whitespace(self, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("  From file.  \n")
        result = self._run_main(["--system-prompt-file", str(prompt_file)], tmp_path)
        assert result == "From file."

    def test_stdin_dash(self, tmp_path):
        result = self._run_main(
            ["--system-prompt-file", "-"], tmp_path, stdin_data="  From stdin.  "
        )
        assert result == "From stdin."

    def test_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PIXTRAL_SYSTEM_PROMPT", "From env.")
        result = self._run_main([], tmp_path)
        assert result == "From env."

    def test_env_var_stripped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PIXTRAL_SYSTEM_PROMPT", "  From env.  ")
        result = self._run_main([], tmp_path)
        assert result == "From env."

    def test_file_takes_precedence_over_inline(self, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("From file.")
        result = self._run_main(
            ["--system-prompt", "Inline.", "--system-prompt-file", str(prompt_file)], tmp_path
        )
        assert result == "From file."

    def test_inline_takes_precedence_over_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PIXTRAL_SYSTEM_PROMPT", "From env.")
        result = self._run_main(["--system-prompt", "Inline."], tmp_path)
        assert result == "Inline."

    def test_file_takes_precedence_over_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PIXTRAL_SYSTEM_PROMPT", "From env.")
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("From file.")
        result = self._run_main(["--system-prompt-file", str(prompt_file)], tmp_path)
        assert result == "From file."

    def test_none_when_nothing_set(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PIXTRAL_SYSTEM_PROMPT", raising=False)
        result = self._run_main([], tmp_path)
        assert result is None
