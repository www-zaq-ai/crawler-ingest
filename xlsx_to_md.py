"""
xlsx_to_md.py — Convert .xlsx / .xls / .csv files to clean markdown.

Uses markitdown[xlsx,xls] for conversion. Each sheet becomes an H2 section
containing a markdown table.

Usage:
    # Single file (all sheets)
    python xlsx_to_md.py report.xlsx

    # Single file with custom output path
    python xlsx_to_md.py report.xlsx --output report.md

    # Entire folder
    python xlsx_to_md.py --input-folder ./sheets --output-folder ./markdown

    # Quiet mode
    python xlsx_to_md.py report.xlsx --quiet
"""

import argparse
import sys
from pathlib import Path

try:
    from markitdown import MarkItDown
except ImportError:
    print("markitdown is not installed. Run: pip install 'markitdown[xlsx,xls]'")
    sys.exit(1)

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

_converter = MarkItDown()


def convert_file(input_path: Path, output_path: Path, quiet: bool = False) -> bool:
    """Convert a single spreadsheet file to markdown. Returns True on success."""
    try:
        result = _converter.convert(str(input_path))
        markdown = result.text_content

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")

        if not quiet:
            print(f"  ✔  {input_path.name}  →  {output_path}")

        return True

    except Exception as e:
        print(f"  ✘  {input_path.name}: {e}", file=sys.stderr)
        return False


def process_folder(
    input_folder: Path,
    output_folder: Path,
    quiet: bool = False,
) -> dict:
    """Convert all spreadsheet files in a folder. Returns a summary dict."""
    files = sorted(
        f for f in input_folder.rglob("*") if f.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not files:
        print(f"No spreadsheet files found in {input_folder}")
        return {"total": 0, "success": 0, "failed": 0}

    success, failed = 0, 0

    for file_path in files:
        relative = file_path.relative_to(input_folder)
        out_path = (output_folder / relative).with_suffix(".md")

        if convert_file(file_path, out_path, quiet):
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
        description="Convert .xlsx / .xls / .csv files to markdown (markitdown).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("input", nargs="?", help="Path to a single spreadsheet file")
    group.add_argument("--input-folder", type=Path, help="Folder containing spreadsheet files")

    parser.add_argument("--output", type=Path, help="Output .md path (single-file mode)")
    parser.add_argument(
        "--output-folder",
        type=Path,
        default=Path("./markdown"),
        help="Output folder (folder mode, default: ./markdown)",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.input_folder:
        input_folder = args.input_folder
        if not input_folder.is_dir():
            parser.error(f"--input-folder does not exist: {input_folder}")

        summary = process_folder(input_folder, args.output_folder, args.quiet)
        sys.exit(0 if summary["failed"] == 0 else 1)

    input_path = Path(args.input)
    if not input_path.is_file():
        parser.error(f"File not found: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        parser.error(
            f"Unsupported file type: {input_path.suffix}. Expected one of {SUPPORTED_EXTENSIONS}"
        )

    output_path = args.output or input_path.with_suffix(".md")
    success = convert_file(input_path, output_path, args.quiet)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
