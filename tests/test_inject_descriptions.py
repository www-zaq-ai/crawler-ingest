"""Unit tests for inject_descriptions.py"""

import json
import pytest
from pathlib import Path

from inject_descriptions import load_descriptions, inject_descriptions


# ---------------------------------------------------------------------------
# load_descriptions
# ---------------------------------------------------------------------------

class TestLoadDescriptions:
    def test_raises_when_file_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_descriptions(str(tmp_path / "nonexistent.json"))

    def test_returns_dict_from_valid_json(self, tmp_path):
        f = tmp_path / "desc.json"
        f.write_text(json.dumps({"img1.png": "A chart.", "img2.png": "A table."}))
        result = load_descriptions(str(f))
        assert result == {"img1.png": "A chart.", "img2.png": "A table."}

    def test_empty_json_object(self, tmp_path):
        f = tmp_path / "desc.json"
        f.write_text("{}")
        assert load_descriptions(str(f)) == {}


# ---------------------------------------------------------------------------
# inject_descriptions
# ---------------------------------------------------------------------------

class TestInjectDescriptions:
    def _write_md(self, tmp_path, content):
        f = tmp_path / "doc.md"
        f.write_text(content)
        return f

    def test_raises_when_md_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            inject_descriptions(str(tmp_path / "missing.md"), {})

    def test_returns_replacement_count(self, tmp_path):
        md = self._write_md(tmp_path, "![alt](img1.png)\n\n![alt](img2.png)")
        _, count = inject_descriptions(str(md), {"img1.png": "Desc one.", "img2.png": "Desc two."})
        assert count == 2

    def test_keeps_image_with_no_description(self, tmp_path):
        md = self._write_md(tmp_path, "![alt](unknown.png)")
        content, count = inject_descriptions(str(md), {})
        assert "unknown.png" in content
        assert count == 0

    def test_skips_error_entries(self, tmp_path):
        md = self._write_md(tmp_path, "![alt](img.png)")
        content, count = inject_descriptions(str(md), {"img.png": "ERROR: API failed"})
        assert "img.png" in content  # original kept
        assert count == 0

    def test_blockquote_format(self, tmp_path):
        md = self._write_md(tmp_path, "![alt](img.png)")
        content, _ = inject_descriptions(str(md), {"img.png": "A diagram."}, format_style="blockquote")
        assert "> **[Image: img.png]**" in content
        assert "> A diagram." in content

    def test_paragraph_format(self, tmp_path):
        md = self._write_md(tmp_path, "![alt](img.png)")
        content, _ = inject_descriptions(str(md), {"img.png": "A diagram."}, format_style="paragraph")
        assert "**[Image: img.png]**" in content
        assert "A diagram." in content

    def test_section_format(self, tmp_path):
        md = self._write_md(tmp_path, "![alt](img.png)")
        content, _ = inject_descriptions(str(md), {"img.png": "A diagram."}, format_style="section")
        assert "#### Image: img.png" in content

    def test_inline_format(self, tmp_path):
        md = self._write_md(tmp_path, "![alt](img.png)")
        content, _ = inject_descriptions(str(md), {"img.png": "A diagram."}, format_style="inline")
        assert "A diagram." in content
        assert "img.png" not in content  # inline omits filename

    def test_collapses_excess_blank_lines(self, tmp_path):
        md = self._write_md(tmp_path, "line1\n\n\n\n\nline2")
        content, _ = inject_descriptions(str(md), {})
        assert "\n\n\n\n" not in content

    def test_writes_to_output_file(self, tmp_path):
        md = self._write_md(tmp_path, "![alt](img.png)")
        out = tmp_path / "out.md"
        inject_descriptions(str(md), {"img.png": "Desc."}, output_file=str(out))
        assert out.exists()
        assert "Desc." in out.read_text()

    def test_overwrites_original_when_no_output(self, tmp_path):
        md = self._write_md(tmp_path, "![alt](img.png)")
        inject_descriptions(str(md), {"img.png": "Desc."})
        assert "Desc." in md.read_text()

    def test_image_filename_matched_by_basename(self, tmp_path):
        """Description lookup uses only the filename, not the full path in the md."""
        md = self._write_md(tmp_path, "![alt](./images/report/img.png)")
        content, count = inject_descriptions(str(md), {"img.png": "Found it."})
        assert count == 1
        assert "Found it." in content
