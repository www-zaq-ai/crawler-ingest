"""Unit tests for docx_to_md.py"""

import re
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

from docx_to_md import (
    _clean_markdown,
    _fully_unescape,
    _normalize_block,
    _table_to_md,
    _build_cell_set,
    _stitch,
    convert_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_table_mock(rows_data):
    """Build a minimal python-docx Table mock from a list of lists of strings."""
    table = MagicMock()
    rows = []
    for row_data in rows_data:
        row = MagicMock()
        cells = []
        for text in row_data:
            cell = MagicMock()
            para = MagicMock()
            para.text = text
            cell.paragraphs = [para]
            cells.append(cell)
        row.cells = cells
        rows.append(row)
    table.rows = rows
    return table


# ---------------------------------------------------------------------------
# _clean_markdown
# ---------------------------------------------------------------------------

class TestCleanMarkdown:
    def test_removes_backslash_escapes(self):
        assert _clean_markdown(r"hello\, world") == "hello, world"

    def test_converts_double_underscore_bold(self):
        assert _clean_markdown("__bold__") == "**bold**"

    def test_preserves_backtick_content(self):
        assert "`code`" in _clean_markdown("`code`")

    def test_preserves_markdown_links(self):
        result = _clean_markdown("[text](url)")
        assert "[text](url)" in result

    def test_empty_string(self):
        assert _clean_markdown("") == ""


# ---------------------------------------------------------------------------
# _fully_unescape
# ---------------------------------------------------------------------------

class TestFullyUnescape:
    def test_strips_all_backslashes(self):
        assert _fully_unescape(r"a\,b\.c") == "a,b.c"

    def test_no_escapes_unchanged(self):
        assert _fully_unescape("hello world") == "hello world"

    def test_double_backslash_becomes_single(self):
        assert _fully_unescape("a\\\\b") == "a\\b"


# ---------------------------------------------------------------------------
# _normalize_block
# ---------------------------------------------------------------------------

class TestNormalizeBlock:
    def test_strips_surrounding_whitespace(self):
        assert _normalize_block("  hello  ") == "hello"

    def test_strips_underscore_bold_markers(self):
        assert _normalize_block("__text__") == "text"

    def test_unescapes_before_normalizing(self):
        assert _normalize_block(r"hello\, world") == "hello, world"


# ---------------------------------------------------------------------------
# _table_to_md
# ---------------------------------------------------------------------------

class TestTableToMd:
    def test_empty_table_returns_empty_string(self):
        table = MagicMock()
        table.rows = []
        assert _table_to_md(table) == ""

    def test_single_header_row(self):
        table = _make_table_mock([["Name", "Value"]])
        result = _table_to_md(table)
        assert "Name" in result
        assert "Value" in result
        assert "|" in result

    def test_header_separator_and_data_row(self):
        table = _make_table_mock([["A", "B"], ["1", "2"]])
        lines = _table_to_md(table).strip().split("\n")
        assert len(lines) == 3
        assert re.match(r"^\|[-| ]+\|$", lines[1])
        assert "1" in lines[2]

    def test_columns_are_padded_to_same_width(self):
        table = _make_table_mock([["Short", "A very long header"], ["x", "y"]])
        result = _table_to_md(table)
        lines = result.split("\n")
        # All data lines should have the same length (pipe-aligned)
        lengths = [len(l) for l in lines if l.strip()]
        assert len(set(lengths)) == 1


# ---------------------------------------------------------------------------
# _build_cell_set
# ---------------------------------------------------------------------------

class TestBuildCellSet:
    def test_collects_all_cell_texts(self):
        table = _make_table_mock([["Alpha", "Beta"], ["Gamma", "Delta"]])
        result = _build_cell_set([table])
        assert result == {"Alpha", "Beta", "Gamma", "Delta"}

    def test_empty_cells_excluded(self):
        table = _make_table_mock([["Hello", ""], ["", "World"]])
        result = _build_cell_set([table])
        assert "" not in result
        assert result == {"Hello", "World"}

    def test_multiple_tables_merged(self):
        t1 = _make_table_mock([["A", "B"]])
        t2 = _make_table_mock([["C", "D"]])
        result = _build_cell_set([t1, t2])
        assert result == {"A", "B", "C", "D"}


# ---------------------------------------------------------------------------
# _stitch
# ---------------------------------------------------------------------------

class TestStitch:
    def test_plain_blocks_pass_through(self):
        result = _stitch(["# Title", "Paragraph text"], [], set())
        assert "# Title" in result
        assert "Paragraph text" in result

    def test_table_replaces_cell_blocks(self):
        cell_texts = {"Cell A", "Cell B"}
        md_table = "| Cell A | Cell B |\n| --- | --- |"
        blocks = ["Intro", "Cell A", "Cell B", "Outro"]
        result = _stitch(blocks, [md_table], cell_texts)
        assert "| Cell A |" in result
        assert "Intro" in result
        assert "Outro" in result
        # Raw cell text should only appear inside the table, not as a separate block
        assert result.count("Cell A") == 1

    def test_trailing_tables_appended_when_no_cell_blocks(self):
        md_table = "| A |\n| - |"
        result = _stitch(["Text"], [md_table], set())
        assert "| A |" in result

    def test_empty_blocks_filtered_out(self):
        result = _stitch(["", "  ", "Hello"], [], set())
        assert result.strip().startswith("Hello")

    def test_multiple_tables_in_order(self):
        cell_texts = {"T1", "T2"}
        tables = ["| T1 |\n| - |", "| T2 |\n| - |"]
        blocks = ["Before", "T1", "Between", "T2", "After"]
        result = _stitch(blocks, tables, cell_texts)
        t1_pos = result.index("T1")
        t2_pos = result.index("T2")
        assert t1_pos < t2_pos


# ---------------------------------------------------------------------------
# convert_file (integration — mocked I/O)
# ---------------------------------------------------------------------------

class TestConvertFile:
    def test_returns_true_on_success(self, tmp_path):
        input_path = tmp_path / "doc.docx"
        input_path.write_bytes(b"fake")
        output_path = tmp_path / "doc.md"

        mammoth_result = MagicMock()
        mammoth_result.value = "# Heading\n\nParagraph."
        mammoth_result.messages = []

        doc_mock = MagicMock()
        doc_mock.tables = []

        with patch("docx_to_md.mammoth.convert_to_markdown", return_value=mammoth_result), \
             patch("docx_to_md.DocxDocument", return_value=doc_mock):
            success = convert_file(input_path, output_path, quiet=True)

        assert success is True
        assert output_path.exists()
        assert "# Heading" in output_path.read_text()

    def test_returns_false_on_exception(self, tmp_path):
        input_path = tmp_path / "bad.docx"
        input_path.write_bytes(b"fake")
        output_path = tmp_path / "bad.md"

        with patch("docx_to_md.mammoth.convert_to_markdown", side_effect=RuntimeError("boom")):
            success = convert_file(input_path, output_path, quiet=True)

        assert success is False
