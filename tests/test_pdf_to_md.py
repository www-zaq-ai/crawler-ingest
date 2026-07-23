"""
Tests for pdf_to_md.py — focusing on pure functions and the Open Data Loader
markdown post-processing (page splitting and image-ref normalisation).
"""

import os
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

import pdf_to_md
from pdf_to_md import (
    classify_page,
    strip_text_keep_images,
    normalize_image_refs,
    split_pages,
)


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
# ensure_java_runtime
# ---------------------------------------------------------------------------

class TestEnsureJavaRuntime:
    """
    Deployment images carry no system JRE, so the loader must be pointed at the
    pip-installed jdk4py runtime.
    """

    def test_system_java_wins_when_present(self):
        with patch("pdf_to_md.shutil.which", return_value="/usr/bin/java"), \
             patch("pdf_to_md._java_usable", return_value=True):
            assert pdf_to_md.ensure_java_runtime() is None

    def test_macos_java_stub_falls_back_to_jdk4py(self, monkeypatch):
        """
        macOS ships a /usr/bin/java stub on every install. It resolves on PATH
        but is not a JVM, so presence must not short-circuit the jdk4py path.
        """
        monkeypatch.setenv("PATH", "/nowhere")

        # Only the stub is unusable — the real jdk4py runtime must still pass.
        def usable(java_bin):
            return str(java_bin) != "/usr/bin/java"

        with patch("pdf_to_md.shutil.which", return_value="/usr/bin/java"), \
             patch("pdf_to_md._java_usable", side_effect=usable):
            java_bin = pdf_to_md.ensure_java_runtime()

        assert java_bin is not None
        assert Path(java_bin).exists()
        assert str(Path(java_bin).parent) in os.environ["PATH"]

    def test_falls_back_to_jdk4py_without_system_java(self, monkeypatch):
        monkeypatch.setenv("PATH", "/nowhere")
        with patch("pdf_to_md.shutil.which", return_value=None):
            java_bin = pdf_to_md.ensure_java_runtime()

        assert java_bin is not None
        assert Path(java_bin).exists(), "jdk4py should ship a real java binary"
        # The loader shells out to bare `java`, so its dir must be on PATH
        assert str(Path(java_bin).parent) in os.environ["PATH"]
        assert os.environ["JAVA_HOME"]

    def test_raises_when_jdk4py_installed_but_unusable(self):
        """
        A wrong-arch wheel or lost exec bit leaves jdk4py importable but not
        runnable. That must fail here with a clear message, not later as an
        opaque non-zero exit from the loader's JAR.
        """
        with patch("pdf_to_md.shutil.which", return_value=None), \
             patch("pdf_to_md._java_usable", return_value=False):
            with pytest.raises(RuntimeError, match="does not run"):
                pdf_to_md.ensure_java_runtime()

    def test_error_message_names_every_candidate_tried(self):
        """The message must not claim 'no java' while one sits on PATH."""
        with patch("pdf_to_md.shutil.which", return_value="/usr/bin/java"), \
             patch("pdf_to_md._java_usable", return_value=False):
            with pytest.raises(RuntimeError) as exc:
                pdf_to_md.ensure_java_runtime()

        message = str(exc.value)
        assert "/usr/bin/java" in message
        assert "jdk4py" in message

    def test_raises_clear_error_when_no_runtime_available(self, monkeypatch):
        """Missing JRE must fail with an actionable message, not a JAR stack trace."""
        import builtins
        real_import = builtins.__import__

        def no_jdk4py(name, *args, **kwargs):
            if name == "jdk4py":
                raise ImportError("no jdk4py")
            return real_import(name, *args, **kwargs)

        with patch("pdf_to_md.shutil.which", return_value=None), \
             patch.object(builtins, "__import__", side_effect=no_jdk4py):
            with pytest.raises(RuntimeError, match="No usable Java runtime found"):
                pdf_to_md.ensure_java_runtime()


# ---------------------------------------------------------------------------
# normalize_image_refs
# ---------------------------------------------------------------------------

class TestNormalizeImageRefs:
    """Open Data Loader emits ![](<relative/path.png>) — angle brackets and all."""

    def test_strips_angle_brackets(self):
        md = "![](<imgs/imageFile1.png>)"
        result = normalize_image_refs(md, "/base")
        assert "<" not in result and ">" not in result
        assert result == "![](/base/imgs/imageFile1.png)"

    def test_resolves_relative_to_base_dir(self):
        result = normalize_image_refs("![alt](<a.png>)", "/base/out")
        assert result == "![alt](/base/out/a.png)"

    def test_preserves_alt_text(self):
        result = normalize_image_refs("![a chart](<x.png>)", "/base")
        assert result.startswith("![a chart](")

    def test_absolute_paths_left_alone(self):
        result = normalize_image_refs("![](</tmp/abs.png>)", "/base")
        assert result == "![](/tmp/abs.png)"

    def test_handles_refs_without_angle_brackets(self):
        result = normalize_image_refs("![](imgs/b.png)", "/base")
        assert result == "![](/base/imgs/b.png)"

    def test_output_matches_downstream_regex(self):
        """clean_md / inject_descriptions use !\\[([^\\]]*)\\]\\(([^\\)]+)\\)."""
        import re
        result = normalize_image_refs("![](<imgs/imageFile1.png>)", "/base")
        match = re.search(r'!\[([^\]]*)\]\(([^\)]+)\)', result)
        assert match is not None
        # The captured path must be usable — no stray bracket in the filename
        assert Path(match.group(2)).name == "imageFile1.png"

    def test_leaves_non_image_text_untouched(self):
        md = "Some text\n\n[a link](http://example.com)\n"
        assert normalize_image_refs(md, "/base") == md

    def test_reanchors_onto_real_image_dir(self):
        """
        Regression: the loader echoes only the last component of --image-dir
        relative to its output dir, so refs must be re-anchored by basename
        onto where the files were actually written — not resolved against the
        (temporary) output dir, which leaves dangling paths.
        """
        md = "![](<good/imageFile1.png>)"
        result = normalize_image_refs(md, "/tmp/scratch", image_dir="/real/images/good")
        assert result == "![](/real/images/good/imageFile1.png)"
        assert "/tmp/scratch" not in result

    def test_image_dir_flattens_nested_refs(self):
        result = normalize_image_refs(
            "![](<a/b/c/img.png>)", "/tmp/scratch", image_dir="/real/imgs"
        )
        assert result == "![](/real/imgs/img.png)"


# ---------------------------------------------------------------------------
# split_pages
# ---------------------------------------------------------------------------

class TestSplitPages:
    def test_splits_on_separator(self):
        md = "<!-- page: 1 -->\n\nfirst\n\n<!-- page: 2 -->\n\nsecond"
        assert split_pages(md) == [(1, "first"), (2, "second")]

    def test_uses_emitted_page_numbers(self):
        """Page numbers come from the loader, not enumeration order."""
        md = "<!-- page: 4 -->\n\nfour\n\n<!-- page: 5 -->\n\nfive"
        assert [n for n, _ in split_pages(md)] == [4, 5]

    def test_no_separator_yields_single_page(self):
        assert split_pages("just content") == [(1, "just content")]

    def test_empty_input_yields_no_pages(self):
        assert split_pages("") == []
        assert split_pages("   \n  ") == []

    def test_preamble_attributed_to_first_page(self):
        md = "title line\n\n<!-- page: 1 -->\n\nbody"
        pages = split_pages(md)
        assert len(pages) == 1
        assert "title line" in pages[0][1]
        assert "body" in pages[0][1]

    def test_empty_trailing_page_preserved(self):
        md = "<!-- page: 1 -->\n\ncontent\n\n<!-- page: 2 -->\n\n"
        assert split_pages(md) == [(1, "content"), (2, "")]

    def test_multipage_content_kept_intact(self):
        md = "<!-- page: 1 -->\n\nline a\nline b\n\n<!-- page: 2 -->\n\nline c"
        pages = split_pages(md)
        assert pages[0][1] == "line a\nline b"
        assert pages[1][1] == "line c"


# ---------------------------------------------------------------------------
# pdf_to_markdown end-to-end (loader mocked)
# ---------------------------------------------------------------------------

def _run_pdf_to_markdown_with_loader_output(md_text):
    """
    Call pdf_to_markdown with the Open Data Loader call mocked out to return
    the given markdown. Returns the written markdown string.
    """
    written = []

    def fake_write_bytes(self, data):
        written.append(data.decode() if isinstance(data, bytes) else data)

    with patch("pdf_to_md.run_open_data_loader", return_value=md_text), \
         patch.object(Path, "write_bytes", fake_write_bytes), \
         patch.object(Path, "exists", return_value=True), \
         patch.object(Path, "mkdir", return_value=None):

        pdf_to_md.pdf_to_markdown(
            "/fake/input.pdf",
            "/fake/output.md",
            write_images=False,
        )

    return "".join(written)


class TestPdfToMarkdown:
    def test_page_separators_emitted(self):
        md = _run_pdf_to_markdown_with_loader_output(
            "<!-- page: 1 -->\n\nPage one content with enough words here yes\n\n"
            "<!-- page: 2 -->\n\nPage two content with enough words here yes"
        )
        assert "<!-- page: 1 -->" in md
        assert "<!-- page: 2 -->" in md

    def test_image_heavy_page_strips_text(self):
        """A page with an image and few words keeps only the image ref."""
        md = _run_pdf_to_markdown_with_loader_output(
            "<!-- page: 1 -->\n\n![](<fig.png>)\n\nshort caption"
        )
        assert "![](" in md
        assert "short caption" not in md

    def test_text_heavy_page_keeps_text(self):
        body = " ".join(["word"] * 40)
        md = _run_pdf_to_markdown_with_loader_output(
            f"<!-- page: 1 -->\n\n![](<fig.png>)\n\n{body}"
        )
        assert "word word" in md

    def test_loader_failure_propagates(self):
        with patch("pdf_to_md.run_open_data_loader", side_effect=RuntimeError("boom")), \
             patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "mkdir", return_value=None):
            with pytest.raises(RuntimeError):
                pdf_to_md.pdf_to_markdown("/fake/in.pdf", "/fake/out.md")

    def test_missing_pdf_raises(self):
        with pytest.raises(FileNotFoundError):
            pdf_to_md.pdf_to_markdown("/definitely/not/here.pdf", "/fake/out.md")
