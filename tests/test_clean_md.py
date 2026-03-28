"""Unit tests for clean_md.py"""

import pytest
from pathlib import Path

from clean_md import load_duplicate_mapping, clean_markdown


# ---------------------------------------------------------------------------
# load_duplicate_mapping
# ---------------------------------------------------------------------------

class TestLoadDuplicateMapping:
    def test_raises_when_file_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_duplicate_mapping(str(tmp_path / "nonexistent.txt"))

    def test_parses_basic_mapping(self, tmp_path):
        f = tmp_path / "mapping.txt"
        f.write_text("dup1.png -> orig1.png\ndup2.png -> orig2.png\n")
        result = load_duplicate_mapping(str(f))
        assert result == {"dup1.png": "orig1.png", "dup2.png": "orig2.png"}

    def test_skips_comments_and_blank_lines(self, tmp_path):
        f = tmp_path / "mapping.txt"
        f.write_text("# comment\n\ndup.png -> orig.png\n")
        result = load_duplicate_mapping(str(f))
        assert result == {"dup.png": "orig.png"}

    def test_extracts_filename_only_from_full_paths(self, tmp_path):
        f = tmp_path / "mapping.txt"
        f.write_text("/images/report/dup.png -> /images/report/orig.png\n")
        result = load_duplicate_mapping(str(f))
        assert result == {"dup.png": "orig.png"}

    def test_empty_file_returns_empty_dict(self, tmp_path):
        f = tmp_path / "mapping.txt"
        f.write_text("")
        assert load_duplicate_mapping(str(f)) == {}

    def test_lines_without_arrow_are_ignored(self, tmp_path):
        f = tmp_path / "mapping.txt"
        f.write_text("not an arrow line\ndup.png -> orig.png\n")
        result = load_duplicate_mapping(str(f))
        assert result == {"dup.png": "orig.png"}


# ---------------------------------------------------------------------------
# clean_markdown
# ---------------------------------------------------------------------------

class TestCleanMarkdown:
    def _write_md(self, tmp_path, content):
        f = tmp_path / "doc.md"
        f.write_text(content)
        return f

    def test_raises_when_md_file_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            clean_markdown(str(tmp_path / "missing.md"), {})

    def test_removes_duplicate_image_references(self, tmp_path):
        md = self._write_md(tmp_path, "![alt](images/dup.png)\n\nSome text.")
        mapping = {"dup.png": "orig.png"}
        content, removed, replaced = clean_markdown(str(md), mapping)
        assert "dup.png" not in content
        assert removed == 1
        assert replaced == 0

    def test_keeps_non_duplicate_images(self, tmp_path):
        md = self._write_md(tmp_path, "![alt](images/unique.png)")
        content, removed, replaced = clean_markdown(str(md), {"dup.png": "orig.png"})
        assert "unique.png" in content
        assert removed == 0

    def test_replace_mode_substitutes_original(self, tmp_path):
        md = self._write_md(tmp_path, "![fig](images/dup.png)")
        mapping = {"dup.png": "orig.png"}
        content, removed, replaced = clean_markdown(str(md), mapping, remove_duplicates=False)
        assert "orig.png" in content
        assert "dup.png" not in content
        assert replaced == 1
        assert removed == 0

    def test_multiple_duplicates_all_removed(self, tmp_path):
        md = self._write_md(tmp_path, "![a](d1.png)\n\n![b](d2.png)\n\n![c](keep.png)")
        mapping = {"d1.png": "orig.png", "d2.png": "orig.png"}
        content, removed, _ = clean_markdown(str(md), mapping)
        assert removed == 2
        assert "keep.png" in content

    def test_collapses_excess_blank_lines(self, tmp_path):
        md = self._write_md(tmp_path, "line1\n\n\n\nline2")
        content, _, _ = clean_markdown(str(md), {})
        assert "\n\n\n" not in content

    def test_writes_to_output_file_when_specified(self, tmp_path):
        md = self._write_md(tmp_path, "![alt](dup.png)")
        out = tmp_path / "out.md"
        clean_markdown(str(md), {"dup.png": "orig.png"}, output_file=str(out))
        assert out.exists()
        assert "dup.png" not in out.read_text()

    def test_overwrites_original_when_no_output_specified(self, tmp_path):
        md = self._write_md(tmp_path, "![alt](dup.png)")
        clean_markdown(str(md), {"dup.png": "orig.png"})
        assert "dup.png" not in md.read_text()
