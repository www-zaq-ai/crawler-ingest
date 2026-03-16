"""
xlsx_to_md.py — Convert .xlsx / .xls / .csv files to natural-language markdown.

Each data row becomes a readable sentence, making the output meaningful
for both vector search and LLM reasoning.

Usage:
    # Single file (all sheets)
    python xlsx_to_md.py report.xlsx

    # Single file with custom output path
    python xlsx_to_md.py report.xlsx --output report.md

    # Specific sheet only
    python xlsx_to_md.py report.xlsx --sheet "Summary"

    # Entire folder
    python xlsx_to_md.py --input-folder ./sheets --output-folder ./markdown

    # Quiet mode
    python xlsx_to_md.py report.xlsx --quiet
"""

import argparse
import sys
import warnings
from pathlib import Path
from typing import Optional

import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


# ---------------------------------------------------------------------------
# Row → sentence helpers
# ---------------------------------------------------------------------------

def _fmt_val(val) -> str:
    """Format a cell value as a human-readable string."""
    if pd.isna(val):
        return ""
    if isinstance(val, pd.Timestamp):
        if val.hour == 0 and val.minute == 0 and val.second == 0:
            return val.strftime("%B %-d, %Y")
        return val.strftime("%B %-d, %Y %H:%M")
    return str(val).strip()


def _row_to_sentence(headers: list, values: list) -> Optional[str]:
    """Turn a single spreadsheet row into a readable sentence."""
    pairs = []
    prefix = ""

    for header, val in zip(headers, values):
        formatted = _fmt_val(val)
        if not formatted:
            continue
        # Unnamed first column is usually a date/index — use as sentence prefix
        if not prefix and header.lower().startswith("unnamed"):
            prefix = f"On {formatted}"
        else:
            pairs.append(f"{header}: {formatted}")

    if not pairs:
        return None

    sentence = ", ".join(pairs) + "."
    return f"{prefix} — {sentence}" if prefix else sentence


def _df_to_section(df: pd.DataFrame, sheet_name: str) -> Optional[str]:
    """Convert a DataFrame to a markdown section of natural-language sentences."""
    df = df.dropna(how="all").dropna(axis=1, how="all")
    if df.empty:
        return None

    headers = [str(c) for c in df.columns]
    sentences = []

    for _, row in df.iterrows():
        sentence = _row_to_sentence(headers, row.tolist())
        if sentence:
            sentences.append(sentence)

    if not sentences:
        return None

    return f"## {sheet_name}\n\n" + "\n".join(sentences)


# ---------------------------------------------------------------------------
# Core conversion
# ---------------------------------------------------------------------------

def convert_file(
    input_path: Path,
    output_path: Path,
    sheet_name: Optional[str] = None,
    quiet: bool = False,
) -> bool:
    """
    Convert a single spreadsheet file to markdown.
    Each sheet becomes a section with an H2 heading.
    Returns True on success.
    """
    try:
        ext = input_path.suffix.lower()
        sections = []

        # ── CSV ───────────────────────────────────────────────────────────────
        if ext == ".csv":
            df = pd.read_csv(input_path)
            section = _df_to_section(df, input_path.stem)
            if section:
                sections.append(section)

        # ── Excel ─────────────────────────────────────────────────────────────
        else:
            xls = pd.ExcelFile(input_path)
            sheets_to_read = [sheet_name] if sheet_name else xls.sheet_names

            missing = [s for s in sheets_to_read if s not in xls.sheet_names]
            if missing:
                print(
                    f"  [warning] Sheet(s) not found and skipped: {', '.join(missing)}",
                    file=sys.stderr,
                )
                sheets_to_read = [s for s in sheets_to_read if s in xls.sheet_names]

            for sheet in sheets_to_read:
                try:
                    df = pd.read_excel(xls, sheet_name=sheet)
                    section = _df_to_section(df, sheet)
                    if section:
                        sections.append(section)
                except Exception as exc:
                    print(f"  [warning] Skipping sheet '{sheet}': {exc}", file=sys.stderr)

        if not sections:
            print(f"  [warning] No content extracted from {input_path.name}", file=sys.stderr)
            return False

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")

        if not quiet:
            print(f"  ✔  {input_path.name}  →  {output_path}")

        return True

    except Exception as e:
        print(f"  ✘  {input_path.name}: {e}", file=sys.stderr)
        return False


def process_folder(
    input_folder: Path,
    output_folder: Path,
    sheet_name: Optional[str] = None,
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

        if convert_file(file_path, out_path, sheet_name, quiet):
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
        description="Convert .xlsx / .xls / .csv files to natural-language markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Input — mutually exclusive: single file vs folder
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("input", nargs="?", help="Path to a single spreadsheet file")
    group.add_argument("--input-folder", type=Path, help="Folder containing spreadsheet files")

    # Output
    parser.add_argument("--output", type=Path, help="Output .md path (single-file mode)")
    parser.add_argument(
        "--output-folder",
        type=Path,
        default=Path("./markdown"),
        help="Output folder (folder mode, default: ./markdown)",
    )

    # Options
    parser.add_argument(
        "--sheet",
        metavar="NAME",
        help="Only convert this sheet name (Excel only, default: all sheets)",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # ── Folder mode ──────────────────────────────────────────────────────────
    if args.input_folder:
        input_folder = args.input_folder
        if not input_folder.is_dir():
            parser.error(f"--input-folder does not exist: {input_folder}")

        summary = process_folder(input_folder, args.output_folder, args.sheet, args.quiet)
        sys.exit(0 if summary["failed"] == 0 else 1)

    # ── Single-file mode ─────────────────────────────────────────────────────
    input_path = Path(args.input)
    if not input_path.is_file():
        parser.error(f"File not found: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        parser.error(
            f"Unsupported file type: {input_path.suffix}. Expected one of {SUPPORTED_EXTENSIONS}"
        )

    output_path = args.output or input_path.with_suffix(".md")
    success = convert_file(input_path, output_path, args.sheet, args.quiet)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()