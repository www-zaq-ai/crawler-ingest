"""Unit tests for pipeline.py"""

import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

from pipeline import PDFPipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pipeline(verbose=False):
    return PDFPipeline(verbose=verbose)


# ---------------------------------------------------------------------------
# PDFPipeline.log
# ---------------------------------------------------------------------------

class TestLog:
    def test_prints_when_verbose(self, capsys):
        p = PDFPipeline(verbose=True)
        p.log("hello")
        assert "hello" in capsys.readouterr().out

    def test_silent_when_not_verbose(self, capsys):
        p = PDFPipeline(verbose=False)
        p.log("hello")
        assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# PDFPipeline.run_command
# ---------------------------------------------------------------------------

def _mock_popen(returncode=0, lines=None):
    """Return a Popen mock that yields lines and exits with returncode."""
    mock_proc = MagicMock()
    mock_proc.stdout.__iter__ = MagicMock(return_value=iter(lines or []))
    mock_proc.wait.return_value = None
    mock_proc.returncode = returncode
    return mock_proc


class TestRunCommand:
    def test_returns_true_on_success(self):
        p = _make_pipeline()
        with patch("pipeline.subprocess.Popen", return_value=_mock_popen(0)):
            assert p.run_command(["echo", "hi"], "test step") is True

    def test_returns_false_on_nonzero_exit(self):
        p = _make_pipeline()
        with patch("pipeline.subprocess.Popen", return_value=_mock_popen(1)):
            assert p.run_command(["bad"], "failing step") is False

    def test_passes_env_with_pythonunbuffered(self):
        p = _make_pipeline()
        with patch("pipeline.subprocess.Popen", return_value=_mock_popen(0)) as mock_popen:
            p.run_command(["cmd"], "step")
            _, kwargs = mock_popen.call_args
            assert kwargs.get("env", {}).get("PYTHONUNBUFFERED") == "1"


# ---------------------------------------------------------------------------
# PDFPipeline.process_single_pdf
# ---------------------------------------------------------------------------

class TestProcessSinglePdf:
    def _patched_pipeline(self, tmp_path, steps_succeed=True, has_images=True, has_duplicates=True):
        """Return a pipeline with run_command and filesystem mocked."""
        p = _make_pipeline()

        # Make each run_command call succeed or fail uniformly
        p.run_command = MagicMock(return_value=steps_succeed)

        # Patch path checks
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"fake")

        images_folder = tmp_path / "images" / "report"
        if has_images:
            images_folder.mkdir(parents=True)
            (images_folder / "fig1.png").write_bytes(b"img")

        if has_duplicates:
            (images_folder / "duplicate_mapping.txt").write_text("dup.png -> orig.png\n")

        return p, pdf, images_folder

    def test_returns_false_when_pdf_not_found(self, tmp_path):
        p = _make_pipeline()
        result = p.process_single_pdf(str(tmp_path / "missing.pdf"))
        assert result is False

    def test_returns_true_on_full_success(self, tmp_path):
        p, pdf, _ = self._patched_pipeline(tmp_path)
        result = p.process_single_pdf(str(pdf), images_dir=str(tmp_path / "images"))
        assert result is True

    def test_returns_false_when_step1_fails(self, tmp_path):
        p, pdf, _ = self._patched_pipeline(tmp_path, steps_succeed=False)
        result = p.process_single_pdf(str(pdf), images_dir=str(tmp_path / "images"))
        assert result is False

    def test_skips_image_steps_when_no_images_extracted(self, tmp_path):
        p, pdf, _ = self._patched_pipeline(tmp_path, has_images=False, has_duplicates=False)
        result = p.process_single_pdf(str(pdf), images_dir=str(tmp_path / "images"))
        # Only step 1 (pdf_to_md) should run
        assert p.run_command.call_count == 1
        assert result is True

    def test_five_steps_run_when_images_and_duplicates_exist(self, tmp_path):
        p, pdf, _ = self._patched_pipeline(tmp_path, has_images=True, has_duplicates=True)
        p.process_single_pdf(str(pdf), images_dir=str(tmp_path / "images"))
        assert p.run_command.call_count == 5

    def test_four_steps_run_when_no_duplicate_mapping(self, tmp_path):
        p, pdf, _ = self._patched_pipeline(tmp_path, has_images=True, has_duplicates=False)
        p.process_single_pdf(str(pdf), images_dir=str(tmp_path / "images"))
        # Steps: 1 pdf_to_md, 2 dedup, 3 image_to_text, 5 inject (step 4 skipped)
        assert p.run_command.call_count == 4

    def test_default_output_md_is_same_stem_as_pdf(self, tmp_path):
        p, pdf, _ = self._patched_pipeline(tmp_path)
        p.process_single_pdf(str(pdf), images_dir=str(tmp_path / "images"))
        first_call_cmd = p.run_command.call_args_list[0][0][0]
        # output md arg should be report.md
        assert any("report.md" in str(arg) for arg in first_call_cmd)


# ---------------------------------------------------------------------------
# PDFPipeline.process_folder
# ---------------------------------------------------------------------------

class TestProcessFolder:
    def test_returns_empty_when_folder_missing(self, tmp_path):
        p = _make_pipeline()
        result = p.process_folder(str(tmp_path / "nope"), str(tmp_path / "out"))
        assert result == {}

    def test_returns_empty_when_no_pdfs(self, tmp_path):
        p = _make_pipeline()
        (tmp_path / "input").mkdir()
        result = p.process_folder(str(tmp_path / "input"), str(tmp_path / "out"))
        assert result == {}

    def test_processes_each_pdf(self, tmp_path):
        inp = tmp_path / "input"
        inp.mkdir()
        (inp / "a.pdf").write_bytes(b"fake")
        (inp / "b.pdf").write_bytes(b"fake")

        p = _make_pipeline()
        p.process_single_pdf = MagicMock(return_value=True)

        result = p.process_folder(str(inp), str(tmp_path / "out"))
        assert p.process_single_pdf.call_count == 2
        assert all(result.values())

    def test_result_reflects_individual_failures(self, tmp_path):
        inp = tmp_path / "input"
        inp.mkdir()
        (inp / "good.pdf").write_bytes(b"fake")
        (inp / "bad.pdf").write_bytes(b"fake")

        p = _make_pipeline()
        # good.pdf succeeds, bad.pdf fails
        p.process_single_pdf = MagicMock(side_effect=lambda path, output_md=None, **kw: "bad" not in path)

        result = p.process_folder(str(inp), str(tmp_path / "out"))
        successes = sum(result.values())
        assert successes == 1
