#!/usr/bin/env python3
"""
PDF to Markdown Converter using PyMuPDF4LLM
Extracts text, tables, and images from PDF files with proper formatting
Optimized for RAG/LLM applications
"""

import pymupdf4llm
import pymupdf as fitz
import sys
import re
import json
import argparse
from pathlib import Path

IMAGE_HEAVY_THRESHOLD = 30


def classify_page(page_text, threshold=IMAGE_HEAVY_THRESHOLD):
    """
    Classify a page as image-heavy or text-heavy.

    Args:
        page_text: Markdown text for a single page
        threshold: Minimum word count to consider a page text-heavy

    Returns:
        Tuple of (page_type, word_count)
    """
    # Count words longer than 1 char that are alphabetic
    words = re.findall(r'\b[a-zA-Z]{2,}\b', page_text)
    word_count = len(words)

    # Check for image references
    has_images = bool(re.search(r'!\[.*?\]\(.*?\)', page_text))

    if has_images and word_count < threshold:
        return 'image_heavy', word_count
    return 'text_heavy', word_count


def strip_text_keep_images(page_text):
    """Strip all text from a page, keeping only image references."""
    lines = page_text.split('\n')
    image_lines = [line for line in lines if re.search(r'!\[.*?\]\(.*?\)', line)]
    return '\n'.join(image_lines)


def get_image_overlap_text(pdf_path):
    """
    Use PyMuPDF to find text spans that overlap with image bounding boxes.

    Returns:
        Dict mapping 1-indexed page numbers to sets of text strings
        that are inside image regions.
    """
    doc = fitz.open(str(pdf_path))
    overlap_text_by_page = {}

    for page_idx in range(len(doc)):
        page = doc[page_idx]

        # Get image bounding boxes
        image_rects = []
        for img_info in page.get_image_info():
            bbox = img_info.get('bbox')
            if bbox:
                image_rects.append(fitz.Rect(bbox))

        if not image_rects:
            continue

        # Get text blocks with positions
        text_dict = page.get_text("dict")
        overlap_texts = set()

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # 0 = text block
                continue
            block_rect = fitz.Rect(block["bbox"])

            for img_rect in image_rects:
                if block_rect.intersects(img_rect):
                    # Collect all text spans from this block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span["text"].strip()
                            if text:
                                overlap_texts.add(text)
                    break

        if overlap_texts:
            overlap_text_by_page[page_idx + 1] = overlap_texts  # 1-indexed

    doc.close()
    return overlap_text_by_page


def strip_image_overlap_text(page_text, overlap_texts):
    """
    Remove lines from markdown whose content matches text found inside image regions.
    Strips markdown formatting before matching.

    Args:
        page_text: Markdown text for a page
        overlap_texts: Set of raw text strings found inside image bounding boxes

    Returns:
        Cleaned markdown text
    """
    if not overlap_texts:
        return page_text

    lines = page_text.split('\n')
    cleaned_lines = []

    for line in lines:
        # Keep image references
        if re.search(r'!\[.*?\]\(.*?\)', line):
            cleaned_lines.append(line)
            continue

        # Strip markdown formatting to get raw text for matching
        raw = line.strip()
        raw = re.sub(r'\*\*(.+?)\*\*', r'\1', raw)  # bold
        raw = re.sub(r'_(.+?)_', r'\1', raw)          # italic
        raw = re.sub(r'\*(.+?)\*', r'\1', raw)        # italic alt
        raw = raw.strip('_* ')

        # Check if this raw text matches any image-overlap text
        if raw and raw in overlap_texts:
            continue  # skip this line

        cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)


def reconstruct_page_tables(doc):
    """
    Use PyMuPDF coordinates to reconstruct table layouts that pymupdf4llm
    reads as disconnected columns. Groups text lines by y-position to pair
    labels with their values.

    Detects layout zones (margins, side panels) and excludes them from the
    main table reconstruction to avoid cross-contamination.

    Args:
        doc: Open fitz.Document

    Returns:
        Dict mapping 0-indexed page numbers to reconstructed markdown text.
        Only includes pages where multi-column table layout was detected.
    """
    from collections import Counter

    Y_TOLERANCE = 4.0       # Points tolerance for same-row grouping
    GAP_THRESHOLD = 10.0    # Minimum x-gap between columns
    MIN_TABLE_ROWS = 3      # Minimum paired rows to consider it a table

    reconstructed = {}

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_width = page.rect.width
        text_dict = page.get_text("dict")

        # Collect all text lines with bounding boxes
        all_lines = []
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line_data in block.get("lines", []):
                text = " ".join(s["text"] for s in line_data["spans"]).strip()
                if not text:
                    continue
                bbox = line_data["bbox"]
                all_lines.append({
                    "text": text,
                    "x0": bbox[0],
                    "x1": bbox[2],
                    "y_center": (bbox[1] + bbox[3]) / 2,
                })

        if not all_lines:
            continue

        # Detect layout zones by clustering x-positions into bins
        # This separates margin text, main content, and side panels
        x_starts = [l["x0"] for l in all_lines]
        x_bins = Counter(round(x / 50) * 50 for x in x_starts)

        # Find the main content zone: the x-range containing the most text
        # Typically the center of the page, excluding far-left margins and far-right panels
        main_bins = sorted(x_bins.keys())

        # Detect side panel: a cluster of text near the right edge (>75% of page width)
        side_panel_threshold = page_width * 0.75
        margin_threshold = page_width * 0.07  # ~40pt for typical pages

        # Filter to main content zone (exclude margins and side panels)
        content_lines = [
            l for l in all_lines
            if l["x0"] >= margin_threshold and l["x0"] < side_panel_threshold
        ]

        # Collect side panel text separately
        side_panel_lines = [l for l in all_lines if l["x0"] >= side_panel_threshold]

        if len(content_lines) < 5:
            continue

        # Sort by y, then group into rows
        content_lines.sort(key=lambda l: (l["y_center"], l["x0"]))
        rows = []
        current_row = [content_lines[0]]

        for line in content_lines[1:]:
            if abs(line["y_center"] - current_row[0]["y_center"]) < Y_TOLERANCE:
                current_row.append(line)
            else:
                rows.append(sorted(current_row, key=lambda l: l["x0"]))
                current_row = [line]
        rows.append(sorted(current_row, key=lambda l: l["x0"]))

        # Count rows with 2+ elements separated by a gap (multi-column indicator)
        multi_col_rows = 0
        gap_positions = []
        for row in rows:
            if len(row) >= 2:
                for i in range(len(row) - 1):
                    gap = row[i + 1]["x0"] - row[i]["x1"]
                    if gap > GAP_THRESHOLD:
                        multi_col_rows += 1
                        gap_positions.append((row[i]["x1"] + row[i + 1]["x0"]) / 2)
                        break

        if multi_col_rows < MIN_TABLE_ROWS:
            continue  # Not a table layout

        # Find the dominant column split point
        if not gap_positions:
            continue
        gap_positions.sort()
        col_boundary = gap_positions[len(gap_positions) // 2]

        # Build markdown output
        md_lines = []
        in_table = False
        last_table_line_idx = -1  # Track last table row for continuation

        # Add side panel as a separate block at the top if present
        if side_panel_lines:
            side_panel_lines.sort(key=lambda l: l["y_center"])
            side_texts = [l["text"] for l in side_panel_lines]
            md_lines.append(" | ".join(side_texts))
            md_lines.append("")

        for row in rows:
            # Split into label (left of boundary) and value (right of boundary)
            label_parts = [e["text"] for e in row if e["x0"] < col_boundary]
            value_parts = [e["text"] for e in row if e["x0"] >= col_boundary]

            label = " ".join(label_parts).strip()
            value = " ".join(value_parts).strip()

            if label and value:
                if not in_table:
                    md_lines.append("\n| | |")
                    md_lines.append("|---|---|")
                    in_table = True
                md_lines.append(f"| {label} | {value} |")
                last_table_line_idx = len(md_lines) - 1
            elif label and not value:
                # Label-only row: could be a section heading or a continuation
                if in_table:
                    md_lines.append("")
                    in_table = False
                md_lines.append(f"\n**{label}**\n")
            elif value and not label:
                # Value-only row: continuation of previous table row's value
                if in_table and last_table_line_idx >= 0:
                    # Append to the previous row's value cell
                    prev = md_lines[last_table_line_idx]
                    # Insert before the trailing " |"
                    prev = prev.rstrip()
                    if prev.endswith("|"):
                        prev = prev[:-1].rstrip() + " " + value + " |"
                    md_lines[last_table_line_idx] = prev
                elif in_table:
                    md_lines.append(f"| | {value} |")
                else:
                    md_lines.append(value)

        if md_lines:
            reconstructed[page_idx] = "\n".join(md_lines)
            print(f"  Page {page_idx + 1}: reconstructed {multi_col_rows} table row(s) from column layout")

    return reconstructed


def pdf_to_markdown(pdf_path, output_path, write_images=False, images_dir=None,
                    image_heavy_threshold=IMAGE_HEAVY_THRESHOLD):
    """
    Convert PDF to Markdown format using pymupdf4llm with page-aware extraction.

    Args:
        pdf_path: Path to input PDF file
        output_path: Path to output MD file
        write_images: Extract and save images separately (default: False)
        images_dir: Base directory for images. Will create subfolder named after PDF
        image_heavy_threshold: Word count below which a page with images is classified
                               as image-heavy (default: 30)
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    print(f"Converting {pdf_path.name}...")

    # Set up image directory if requested
    image_path = None
    if write_images and images_dir:
        images_dir = Path(images_dir)
        # Create subfolder with PDF filename (without extension)
        pdf_folder_name = pdf_path.stem
        image_path = images_dir / pdf_folder_name
        image_path.mkdir(parents=True, exist_ok=True)
        print(f"  Images will be saved to: {image_path}")

    # Convert PDF to markdown using page_chunks mode for page-aware extraction
    page_chunks = pymupdf4llm.to_markdown(
        str(pdf_path),
        write_images=write_images,
        image_path=str(image_path) if image_path else None,
        page_chunks=True
    )

    # Detect text that overlaps with image bounding boxes (for cleanup on text-heavy pages)
    overlap_text_by_page = get_image_overlap_text(pdf_path)
    if overlap_text_by_page:
        total = sum(len(v) for v in overlap_text_by_page.values())
        print(f"  Found {total} text fragment(s) inside image regions across {len(overlap_text_by_page)} page(s)")

    # Reconstruct table layouts from coordinate analysis
    doc = fitz.open(str(pdf_path))
    reconstructed_pages = reconstruct_page_tables(doc)
    doc.close()

    md_parts = []
    page_classification = {}

    for i, chunk in enumerate(page_chunks):
        # pymupdf4llm <0.0.17: chunk['metadata']['page'] (1-indexed)
        # pymupdf4llm >=0.0.17: chunk['page'] (0-indexed, top-level)
        meta_page = chunk.get('metadata', {}).get('page')
        if meta_page is not None:
            page_num = meta_page
        else:
            page_num = chunk.get('page', i) + 1
        fitz_page_idx = page_num - 1                  # 0-indexed for fitz lookups
        page_text = chunk['text']

        page_type, word_count = classify_page(page_text, image_heavy_threshold)

        # Find images referenced in this page
        images_in_page = re.findall(r'!\[.*?\]\((.*?)\)', page_text)
        image_names = [Path(img).name for img in images_in_page]

        page_classification[str(page_num)] = {
            'type': page_type,
            'word_count': word_count,
            'images': image_names
        }

        print(f"  Page {page_num}: {page_type} (words: {word_count}, images: {len(image_names)})")

        # Add page separator
        md_parts.append(f'<!-- page: {page_num} -->')

        if page_type == 'image_heavy':
            # Strip text artifacts, keep only image references
            # Pixtral will be the sole content source for this page
            md_parts.append(strip_text_keep_images(page_text))
        elif fitz_page_idx in reconstructed_pages:
            # Use coordinate-reconstructed table layout instead of pymupdf4llm text
            # Preserve any image references from the original text
            image_refs = [line for line in page_text.split('\n')
                         if re.search(r'!\[.*?\]\(.*?\)', line)]
            reconstructed = reconstructed_pages[fitz_page_idx]
            if image_refs:
                reconstructed = '\n'.join(image_refs) + '\n\n' + reconstructed
            md_parts.append(reconstructed)
        else:
            # Strip text that overlaps with image regions (OCR artifacts from diagrams)
            overlap_texts = overlap_text_by_page.get(page_num, set())
            if overlap_texts:
                page_text = strip_image_overlap_text(page_text, overlap_texts)
                print(f"    Stripped {len(overlap_texts)} image-region text fragment(s)")
            md_parts.append(page_text)

    md_text = '\n\n'.join(md_parts)

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to markdown file
    output_path.write_bytes(md_text.encode())

    print(f"✓ Saved to: {output_path}")
    if image_path:
        print(f"✓ Images saved to: {image_path}")

    # Write page classification manifest for downstream tools
    if image_path:
        classification_path = image_path / 'page_classification.json'
        with open(classification_path, 'w', encoding='utf-8') as f:
            json.dump(page_classification, f, indent=2)
        print(f"✓ Page classification saved to: {classification_path}")

    return output_path


def process_folder(input_folder, output_folder, write_images=False, images_dir=None,
                   image_heavy_threshold=IMAGE_HEAVY_THRESHOLD):
    """
    Process all PDF files in a folder

    Args:
        input_folder: Path to folder containing PDF files
        output_folder: Path to folder for output MD files
        write_images: Extract and save images separately
        images_dir: Base directory for images (each PDF gets its own subfolder)
        image_heavy_threshold: Word count threshold for image-heavy classification
    """
    input_folder = Path(input_folder)
    output_folder = Path(output_folder)

    if not input_folder.exists():
        raise FileNotFoundError(f"Input folder not found: {input_folder}")

    # Find all PDF files
    pdf_files = list(input_folder.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in {input_folder}")
        return

    print(f"Found {len(pdf_files)} PDF file(s)")
    print(f"Output folder: {output_folder}")
    if write_images and images_dir:
        print(f"Images folder: {images_dir}")
    print("-" * 50)

    # Create output folder
    output_folder.mkdir(parents=True, exist_ok=True)

    # Process each PDF
    success_count = 0
    for pdf_file in pdf_files:
        output_file = output_folder / pdf_file.with_suffix('.md').name
        try:
            pdf_to_markdown(pdf_file, output_file, write_images=write_images,
                          images_dir=images_dir,
                          image_heavy_threshold=image_heavy_threshold)
            success_count += 1
        except Exception as e:
            print(f"✗ Error processing {pdf_file.name}: {e}")

    print("-" * 50)
    print(f"Completed: {success_count}/{len(pdf_files)} files converted")


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF files to Markdown format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Single file:
    python pdf_to_md.py input.pdf output.md
  
  Batch process folder:
    python pdf_to_md.py --input-folder files --output-folder output_files
  
  With image extraction:
    python pdf_to_md.py input.pdf output.md --with-images --images-dir ./images
    
  Batch with images:
    python pdf_to_md.py --input-folder files --output-folder output_files --with-images --images-dir ./images
        """
    )
    
    parser.add_argument('input', nargs='?', help='Input PDF file')
    parser.add_argument('output', nargs='?', help='Output MD file')
    parser.add_argument('--input-folder', help='Input folder containing PDF files')
    parser.add_argument('--output-folder', help='Output folder for MD files')
    parser.add_argument('--with-images', action='store_true', help='Extract and save images')
    parser.add_argument('--images-dir', help='Base directory for images (subfolder per PDF will be created)')
    parser.add_argument('--image-heavy-threshold', type=int, default=IMAGE_HEAVY_THRESHOLD,
                       help=f'Word count below which a page with images is image-heavy (default: {IMAGE_HEAVY_THRESHOLD})')

    args = parser.parse_args()

    try:
        # Batch processing mode
        if args.input_folder and args.output_folder:
            process_folder(args.input_folder, args.output_folder, args.with_images,
                         args.images_dir, args.image_heavy_threshold)

        # Single file mode
        elif args.input:
            if not args.output:
                output = Path(args.input).with_suffix('.md')
            else:
                output = args.output
            pdf_to_markdown(args.input, output, args.with_images, args.images_dir,
                          args.image_heavy_threshold)
        
        else:
            parser.print_help()
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()