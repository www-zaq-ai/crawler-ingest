#!/usr/bin/env python3
"""
Generate a small valid PDF for exercising pdf_to_md.py by hand.

The repo's only crawled PDF is truncated and Open Data Loader rejects it, so
there is nothing checked in that a manual smoke test can use. This writes a
two-page file: page 1 text + a table-ish layout, page 2 an image with a short
caption (which should classify as image_heavy).

    python tests/make_sample_pdf.py /tmp/sample.pdf

Requires pymupdf, which is no longer a pipeline dependency — install it ad hoc
if you need this:  pip install pymupdf
"""

import sys
from pathlib import Path


def make_sample_pdf(out_path):
    import pymupdf

    doc = pymupdf.open()

    page = doc.new_page()
    page.insert_text((72, 100), "Quarterly Report 2026", fontsize=20)
    page.insert_text((72, 140), "Revenue grew across all regions this quarter.", fontsize=11)
    y = 180
    for label, value in [("Region", "Revenue"), ("North", "1200"),
                         ("South", "900"), ("East", "1500")]:
        page.insert_text((72, y), label, fontsize=11)
        page.insert_text((250, y), value, fontsize=11)
        y += 20

    page2 = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 240, 160))
    pix.set_rect(pix.irect, (200, 60, 60))
    page2.insert_image(pymupdf.Rect(72, 72, 312, 232), pixmap=pix)
    page2.insert_text((72, 260), "Figure 1: regional breakdown chart.", fontsize=11)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path, len(doc)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "/tmp/sample.pdf"
    path, pages = make_sample_pdf(target)
    print(f"Wrote {pages}-page sample PDF to {path}")
