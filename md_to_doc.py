"""
md_to_doc.py — Convert markdown files back into documents (the inverse of the
*_to_md.py converters).

Routes each target format to an engine via `--to`. Currently supported:

    pdf   → markdown-pdf (renders in-process via PyMuPDF — fully self-contained,
            no external PDF engine, no system binaries)

Usage:
    # Single file  (report.md → report.pdf)
    python md_to_doc.py report.md

    # Explicit target + custom output path
    python md_to_doc.py report.md --to pdf --output report.pdf

    # Include a table-of-contents page / PDF bookmarks
    python md_to_doc.py report.md --toc

    # Entire folder
    python md_to_doc.py --input-folder ./markdown --output-folder ./pdfs

    # Quiet mode
    python md_to_doc.py report.md --quiet
"""

import argparse
import sys
from pathlib import Path

try:
    from markdown_pdf import MarkdownPdf, Section
except ImportError:
    print(
        "markdown-pdf is not installed. Run: pip install 'markdown-pdf==1.13.2'",
        file=sys.stderr,
    )
    sys.exit(1)

SUPPORTED_INPUT_EXTENSIONS = {".md", ".markdown"}

# Maps a --to target to the output file extension. pdf is the only self-contained
# format; extend this only with engines that need no external binaries.
SUPPORTED_FORMATS = {"pdf": ".pdf"}

# markdown-pdf ships no table borders by default, so multi-column tables render
# as loosely-aligned text. This stylesheet gives tables real gridlines and
# padding. (No cell background colors — markdown-pdf/PyMuPDF bleeds them into
# adjacent lines; headers are already bold, so borders alone read cleanly.)
# Override the whole thing with --css.
DEFAULT_CSS = """
table { border-collapse: collapse; margin: 8px 0; }
th, td { border: 1px solid #999; padding: 4px 8px; text-align: left;
         vertical-align: top; }
"""


def convert_file(
    input_path: Path,
    output_path: Path,
    fmt: str = "pdf",
    toc: bool = False,
    css: str = DEFAULT_CSS,
    quiet: bool = False,
) -> bool:
    """Convert a single markdown file to `fmt`. Returns True on success."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        text = input_path.read_text(encoding="utf-8")

        # gfm-like enables tables / strikethrough (markdown produced by the
        # *_to_md.py converters uses GitHub-flavored tables).
        pdf = MarkdownPdf(toc_level=6 if toc else 0, mode="gfm-like")
        # root lets relative image paths in the markdown resolve from the file's
        # own folder rather than the process CWD.
        pdf.add_section(
            Section(text, toc=toc, root=str(input_path.parent)),
            user_css=css or None,
        )
        pdf.save(str(output_path))

        if not quiet:
            print(f"  ✔  {input_path.name}  →  {output_path}")
        return True

    except Exception as e:
        print(f"  ✘  {input_path.name}: {e}", file=sys.stderr)
        return False


def process_folder(
    input_folder: Path,
    output_folder: Path,
    fmt: str = "pdf",
    toc: bool = False,
    css: str = DEFAULT_CSS,
    quiet: bool = False,
) -> dict:
    """Convert all markdown files in a folder. Returns a summary dict."""
    files = sorted(
        f
        for f in input_folder.rglob("*")
        if f.suffix.lower() in SUPPORTED_INPUT_EXTENSIONS
    )

    if not files:
        print(f"No markdown files found in {input_folder}")
        return {"total": 0, "success": 0, "failed": 0}

    ext = SUPPORTED_FORMATS[fmt]
    success, failed = 0, 0

    for md_path in files:
        relative = md_path.relative_to(input_folder)
        out_path = (output_folder / relative).with_suffix(ext)

        if convert_file(md_path, out_path, fmt, toc, css, quiet):
            success += 1
        else:
            failed += 1

    summary = {"total": len(files), "success": success, "failed": failed}

    if not quiet:
        print(
            f"\nDone — {success}/{len(files)} converted"
            + (f", {failed} failed" if failed else "")
        )

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert markdown files to documents (self-contained, markdown-pdf).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("input", nargs="?", help="Path to a single markdown file")
    group.add_argument(
        "--input-folder", type=Path, help="Folder containing markdown files"
    )

    parser.add_argument(
        "--to",
        choices=sorted(SUPPORTED_FORMATS),
        default="pdf",
        help="Target format (default: pdf)",
    )
    parser.add_argument("--output", type=Path, help="Output path (single-file mode)")
    parser.add_argument(
        "--output-folder",
        type=Path,
        default=Path("./documents"),
        help="Output folder (folder mode, default: ./documents)",
    )
    parser.add_argument(
        "--toc",
        action="store_true",
        help="Add a table-of-contents page and PDF bookmarks",
    )
    parser.add_argument(
        "--css",
        type=Path,
        help="Path to a CSS file to style the output (replaces the built-in "
        "default stylesheet, which gives tables borders + a shaded header row)",
    )
    parser.add_argument(
        "--no-css",
        action="store_true",
        help="Disable the built-in default stylesheet (bare markdown-pdf output)",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.css and args.no_css:
        parser.error("--css and --no-css are mutually exclusive")
    if args.css:
        if not args.css.is_file():
            parser.error(f"--css file not found: {args.css}")
        css = args.css.read_text(encoding="utf-8")
    elif args.no_css:
        css = ""
    else:
        css = DEFAULT_CSS

    if args.input_folder:
        input_folder = args.input_folder
        if not input_folder.is_dir():
            parser.error(f"--input-folder does not exist: {input_folder}")

        summary = process_folder(
            input_folder, args.output_folder, args.to, args.toc, css, args.quiet
        )
        sys.exit(0 if summary["failed"] == 0 else 1)

    input_path = Path(args.input)
    if not input_path.is_file():
        parser.error(f"File not found: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_INPUT_EXTENSIONS:
        parser.error(
            f"Expected a markdown file ({', '.join(sorted(SUPPORTED_INPUT_EXTENSIONS))}), "
            f"got: {input_path.suffix}"
        )

    output_path = args.output or input_path.with_suffix(SUPPORTED_FORMATS[args.to])
    success = convert_file(input_path, output_path, args.to, args.toc, css, args.quiet)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
