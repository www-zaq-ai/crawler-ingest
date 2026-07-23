"""Unit tests for xlsx_to_md.py"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from xlsx_to_md import convert_file, process_folder, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_convert_result(text: str) -> MagicMock:
    result = MagicMock()
    result.text_content = text
    return result


# ---------------------------------------------------------------------------
# convert_file
# ---------------------------------------------------------------------------

class TestConvertFile:
    def test_returns_true_and_writes_markdown(self, tmp_path):
        input_path = tmp_path / "report.xlsx"
        input_path.write_bytes(b"fake")
        output_path = tmp_path / "report.md"

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("## Sheet1\n\nHello")):
            success = convert_file(input_path, output_path, quiet=True)

        assert success is True
        assert output_path.exists()
        assert "## Sheet1" in output_path.read_text()

    def test_creates_output_parent_dirs(self, tmp_path):
        input_path = tmp_path / "report.xlsx"
        input_path.write_bytes(b"fake")
        output_path = tmp_path / "nested" / "deep" / "report.md"

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("content")):
            success = convert_file(input_path, output_path, quiet=True)

        assert success is True
        assert output_path.exists()

    def test_returns_false_on_exception(self, tmp_path):
        input_path = tmp_path / "bad.xlsx"
        input_path.write_bytes(b"fake")
        output_path = tmp_path / "bad.md"

        with patch("xlsx_to_md._converter.convert", side_effect=RuntimeError("boom")):
            success = convert_file(input_path, output_path, quiet=True)

        assert success is False
        assert not output_path.exists()

    def test_quiet_suppresses_output(self, tmp_path, capsys):
        input_path = tmp_path / "report.xlsx"
        input_path.write_bytes(b"fake")
        output_path = tmp_path / "report.md"

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("hi")):
            convert_file(input_path, output_path, quiet=True)

        assert capsys.readouterr().out == ""

    def test_verbose_prints_success(self, tmp_path, capsys):
        input_path = tmp_path / "report.xlsx"
        input_path.write_bytes(b"fake")
        output_path = tmp_path / "report.md"

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("hi")):
            convert_file(input_path, output_path, quiet=False)

        out = capsys.readouterr().out
        assert "report.xlsx" in out

    def test_writes_correct_encoding(self, tmp_path):
        input_path = tmp_path / "report.xlsx"
        input_path.write_bytes(b"fake")
        output_path = tmp_path / "report.md"
        content = "Héllo wörld — em dash"

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result(content)):
            convert_file(input_path, output_path, quiet=True)

        assert output_path.read_text(encoding="utf-8") == content

    def test_passes_input_path_to_markitdown(self, tmp_path):
        input_path = tmp_path / "report.xlsx"
        input_path.write_bytes(b"fake")

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("x")) as conv:
            convert_file(input_path, tmp_path / "report.md", quiet=True)

        conv.assert_called_once_with(str(input_path))

    @pytest.mark.parametrize("suffix", [".xlsx", ".xls", ".csv"])
    def test_converts_every_supported_extension(self, tmp_path, suffix):
        input_path = (tmp_path / "data").with_suffix(suffix)
        input_path.write_bytes(b"fake")
        output_path = tmp_path / "data.md"

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("## S")):
            success = convert_file(input_path, output_path, quiet=True)

        assert success is True
        assert output_path.read_text() == "## S"


# ---------------------------------------------------------------------------
# process_folder
# ---------------------------------------------------------------------------

class TestProcessFolder:
    def test_no_spreadsheet_files_returns_zero_total(self, tmp_path):
        result = process_folder(tmp_path, tmp_path / "out", quiet=True)
        assert result == {"total": 0, "success": 0, "failed": 0}

    def test_single_file_success(self, tmp_path):
        (tmp_path / "sheet.xlsx").write_bytes(b"fake")
        out_dir = tmp_path / "out"

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("## Sheet1")):
            result = process_folder(tmp_path, out_dir, quiet=True)

        assert result == {"total": 1, "success": 1, "failed": 0}
        assert (out_dir / "sheet.md").exists()

    def test_multiple_files_all_succeed(self, tmp_path):
        for name in ("a.xlsx", "b.xlsx", "c.xlsx"):
            (tmp_path / name).write_bytes(b"fake")
        out_dir = tmp_path / "out"

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("| a | b |")):
            result = process_folder(tmp_path, out_dir, quiet=True)

        assert result["total"] == 3
        assert result["success"] == 3
        assert result["failed"] == 0

    def test_partial_failure_counted(self, tmp_path):
        (tmp_path / "good.xlsx").write_bytes(b"fake")
        (tmp_path / "bad.xlsx").write_bytes(b"fake")
        out_dir = tmp_path / "out"

        def _side_effect(path):
            if "bad" in str(path):
                raise RuntimeError("corrupt")
            return _make_convert_result("ok")

        with patch("xlsx_to_md._converter.convert", side_effect=_side_effect):
            result = process_folder(tmp_path, out_dir, quiet=True)

        assert result["total"] == 2
        assert result["success"] == 1
        assert result["failed"] == 1

    def test_preserves_subfolder_structure(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.xlsx").write_bytes(b"fake")
        out_dir = tmp_path / "out"

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("x")):
            process_folder(tmp_path, out_dir, quiet=True)

        assert (out_dir / "sub" / "nested.md").exists()

    def test_verbose_prints_summary(self, tmp_path, capsys):
        (tmp_path / "sheet.xlsx").write_bytes(b"fake")

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("x")):
            process_folder(tmp_path, tmp_path / "out", quiet=False)

        assert "1/1" in capsys.readouterr().out

    def test_collects_all_supported_extensions(self, tmp_path):
        for name in ("a.xlsx", "b.xls", "c.csv"):
            (tmp_path / name).write_bytes(b"fake")
        out_dir = tmp_path / "out"

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("x")):
            result = process_folder(tmp_path, out_dir, quiet=True)

        assert result == {"total": 3, "success": 3, "failed": 0}
        assert {p.name for p in out_dir.iterdir()} == {"a.md", "b.md", "c.md"}

    def test_ignores_unsupported_extensions(self, tmp_path):
        (tmp_path / "keep.xlsx").write_bytes(b"fake")
        for name in ("notes.txt", "readme.md", "scan.pdf", "deck.pptx"):
            (tmp_path / name).write_bytes(b"fake")
        out_dir = tmp_path / "out"

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("x")):
            result = process_folder(tmp_path, out_dir, quiet=True)

        assert result == {"total": 1, "success": 1, "failed": 0}
        assert {p.name for p in out_dir.iterdir()} == {"keep.md"}

    def test_matches_extensions_case_insensitively(self, tmp_path):
        (tmp_path / "loud.XLSX").write_bytes(b"fake")
        out_dir = tmp_path / "out"

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("x")):
            result = process_folder(tmp_path, out_dir, quiet=True)

        assert result == {"total": 1, "success": 1, "failed": 0}


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------

class TestMain:
    def test_single_file_success(self, tmp_path, monkeypatch):
        xlsx = tmp_path / "sheet.xlsx"
        xlsx.write_bytes(b"fake")
        monkeypatch.setattr("sys.argv", ["xlsx_to_md.py", str(xlsx)])

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("# Hi")):
            with pytest.raises(SystemExit) as exc:
                main()

        assert exc.value.code == 0
        assert xlsx.with_suffix(".md").exists()

    def test_custom_output_path(self, tmp_path, monkeypatch):
        xlsx = tmp_path / "sheet.xlsx"
        xlsx.write_bytes(b"fake")
        out = tmp_path / "custom.md"
        monkeypatch.setattr("sys.argv", ["xlsx_to_md.py", str(xlsx), "--output", str(out)])

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("hi")):
            with pytest.raises(SystemExit) as exc:
                main()

        assert exc.value.code == 0
        assert out.exists()

    def test_wrong_extension_exits_nonzero(self, tmp_path, monkeypatch):
        f = tmp_path / "file.pptx"
        f.write_bytes(b"fake")
        monkeypatch.setattr("sys.argv", ["xlsx_to_md.py", str(f)])

        with pytest.raises(SystemExit) as exc:
            main()

        assert exc.value.code != 0

    def test_missing_file_exits_nonzero(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.argv", ["xlsx_to_md.py", str(tmp_path / "ghost.xlsx")])

        with pytest.raises(SystemExit) as exc:
            main()

        assert exc.value.code != 0

    @pytest.mark.parametrize("suffix", [".xlsx", ".xls", ".csv"])
    def test_accepts_every_supported_extension(self, tmp_path, monkeypatch, suffix):
        src = (tmp_path / "data").with_suffix(suffix)
        src.write_bytes(b"fake")
        monkeypatch.setattr("sys.argv", ["xlsx_to_md.py", str(src)])

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("x")):
            with pytest.raises(SystemExit) as exc:
                main()

        assert exc.value.code == 0
        assert src.with_suffix(".md").exists()

    def test_sheet_flag_is_no_longer_accepted(self, tmp_path, monkeypatch):
        """--sheet was dropped: markitdown converts the whole workbook in one pass."""
        src = tmp_path / "report.xlsx"
        src.write_bytes(b"fake")
        monkeypatch.setattr("sys.argv", ["xlsx_to_md.py", str(src), "--sheet", "Summary"])

        with pytest.raises(SystemExit) as exc:
            main()

        assert exc.value.code != 0

    def test_folder_mode_success(self, tmp_path, monkeypatch):
        (tmp_path / "a.xlsx").write_bytes(b"fake")
        out_dir = tmp_path / "out"
        monkeypatch.setattr(
            "sys.argv",
            ["xlsx_to_md.py", "--input-folder", str(tmp_path), "--output-folder", str(out_dir)],
        )

        with patch("xlsx_to_md._converter.convert", return_value=_make_convert_result("hi")):
            with pytest.raises(SystemExit) as exc:
                main()

        assert exc.value.code == 0
        assert (out_dir / "a.md").exists()

    def test_folder_mode_missing_dir_exits_nonzero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            ["xlsx_to_md.py", "--input-folder", str(tmp_path / "nope")],
        )

        with pytest.raises(SystemExit) as exc:
            main()

        assert exc.value.code != 0

    def test_folder_mode_partial_failure_exits_nonzero(self, tmp_path, monkeypatch):
        (tmp_path / "bad.xlsx").write_bytes(b"fake")
        out_dir = tmp_path / "out"
        monkeypatch.setattr(
            "sys.argv",
            ["xlsx_to_md.py", "--input-folder", str(tmp_path), "--output-folder", str(out_dir)],
        )

        with patch("xlsx_to_md._converter.convert", side_effect=RuntimeError("boom")):
            with pytest.raises(SystemExit) as exc:
                main()

        assert exc.value.code != 0
