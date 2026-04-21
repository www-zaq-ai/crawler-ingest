"""
pptx_to_md.py — Convert .pptx files to clean markdown.

Uses markitdown[pptx] for conversion.

Usage:
    # Single file
    python pptx_to_md.py report.pptx

    # Single file with custom output path
    python pptx_to_md.py report.pptx --output report.md

    # Entire folder
    python pptx_to_md.py --input-folder ./slides --output-folder ./markdown

    # Quiet mode
    python pptx_to_md.py report.pptx --quiet
"""

import argparse
import sys
from pathlib import Path

try:
    from markitdown import MarkItDown
except ImportError:
    print("markitdown is not installed. Run: pip install 'markitdown[pptx]'")
    sys.exit(1)

_converter = MarkItDown()


def convert_file(input_path: Path, output_path: Path, quiet: bool = False) -> bool:
    """Convert a single .pptx file to markdown. Returns True on success."""
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
    """Convert all .pptx files in a folder. Returns a summary dict."""
    pptx_files = sorted(input_folder.rglob("*.pptx"))

    if not pptx_files:
        print(f"No .pptx files found in {input_folder}")
        return {"total": 0, "success": 0, "failed": 0}

    success, failed = 0, 0

    for pptx_path in pptx_files:
        relative = pptx_path.relative_to(input_folder)
        out_path = (output_folder / relative).with_suffix(".md")

        if convert_file(pptx_path, out_path, quiet):
            success += 1
        else:
            failed += 1

    summary = {"total": len(pptx_files), "success": success, "failed": failed}

    if not quiet:
        print(
            f"\nDone — {success}/{len(pptx_files)} converted"
            + (f", {failed} failed" if failed else "")
        )

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert .pptx files to markdown (markitdown).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("input", nargs="?", help="Path to a single .pptx file")
    group.add_argument("--input-folder", type=Path, help="Folder containing .pptx files")

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
    if input_path.suffix.lower() != ".pptx":
        parser.error(f"Expected a .pptx file, got: {input_path.suffix}")

    output_path = args.output or input_path.with_suffix(".md")
    success = convert_file(input_path, output_path, args.quiet)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
