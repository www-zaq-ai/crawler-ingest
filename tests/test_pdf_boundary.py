"""
Boundary test: crawler-ingest hands the PDF to Open Data Loader untouched.

Open Data Loader owns interpretation of the PDF. crawler-ingest only
orchestrates, so the bytes reaching `opendataloader_pdf.convert(...)` must be
byte-for-byte the bytes the caller supplied. Only `convert` is replaced here;
every crawler stage before it runs for real.
"""

import hashlib
import shutil
import sys
from pathlib import Path

import pytest

import pdf_to_md


FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"
# Pinned so a silently regenerated or corrupted fixture fails loudly instead
# of turning the byte-equality assertions into a comparison of two wrong files.
FIXTURE_SHA256 = "84da995d33245dab0588dfe58ffa94790172ce4d651ae60509f225ac8c46d765"


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _call_function(src, out, images_dir):
    pdf_to_md.pdf_to_markdown(src, out, write_images=True, images_dir=images_dir)


def _call_cli(src, out, images_dir, monkeypatch):
    # Same argv pipeline.py builds for step 1.
    monkeypatch.setattr(sys, "argv", [
        "pdf_to_md.py", str(src), str(out),
        "--with-images", "--images-dir", str(images_dir),
    ])
    pdf_to_md.main()


@pytest.fixture
def spy_convert(monkeypatch):
    """
    Replace opendataloader_pdf.convert with a spy that snapshots the input
    file at call time, then writes the minimal markdown the caller reads back.
    """
    calls = []

    def fake_convert(**kwargs):
        input_path = Path(kwargs["input_path"])
        data = input_path.read_bytes()
        calls.append({
            "kwargs": kwargs,
            "input_path": input_path,
            "bytes": data,
            "sha256": _sha256(data),
        })
        out_dir = Path(kwargs["output_dir"])
        (out_dir / f"{input_path.stem}.md").write_text(
            "<!-- page: 1 -->\n\nstub page one\n", encoding="utf-8"
        )

    monkeypatch.setattr(pdf_to_md.opendataloader_pdf, "convert", fake_convert)
    return calls


@pytest.mark.parametrize("entry", ["function", "cli"])
def test_pdf_reaches_open_data_loader_byte_for_byte(
    entry, spy_convert, tmp_path, monkeypatch
):
    fixture_bytes = FIXTURE.read_bytes()
    assert _sha256(fixture_bytes) == FIXTURE_SHA256
    assert fixture_bytes.startswith(b"%PDF-")

    # Work on a copy so a mutating regression cannot corrupt the checked-in
    # fixture; the copy is the "source" the crawler is handed.
    src = tmp_path / "in" / "sample.pdf"
    src.parent.mkdir()
    shutil.copyfile(FIXTURE, src)
    out = tmp_path / "out" / "sample.md"
    images_dir = tmp_path / "images"

    if entry == "function":
        _call_function(src, out, images_dir)
    else:
        _call_cli(src, out, images_dir, monkeypatch)

    assert len(spy_convert) == 1
    call = spy_convert[0]

    # The loader is pointed straight at the caller's file — no temp copy.
    assert call["input_path"].resolve() == src.resolve()

    # Byte equality is the invariant.
    assert call["bytes"] == fixture_bytes
    assert call["sha256"] == FIXTURE_SHA256

    # Neither the source nor the fixture was rewritten by the run.
    assert src.read_bytes() == fixture_bytes
    assert _sha256(FIXTURE.read_bytes()) == FIXTURE_SHA256

    # The surrounding crawler code finished on the stub output.
    assert "stub page one" in out.read_text(encoding="utf-8")
