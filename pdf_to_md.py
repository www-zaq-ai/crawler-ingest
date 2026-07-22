#!/usr/bin/env python3
"""
PDF to Markdown Converter using Open Data Loader
Extracts text, tables, and images from PDF files with proper formatting
Optimized for RAG/LLM applications

Open Data Loader ships a Python API (`opendataloader_pdf.convert`) over a
bundled extraction engine. A JRE 11+ must be on PATH — see README.
"""

import os
import re
import sys
import json
import shutil
import argparse
import tempfile
from pathlib import Path


def ensure_java_runtime():
    """
    Make a JVM reachable to Open Data Loader, which shells out to bare `java`.

    Deployment containers install this pipeline with `pip install -r
    requirements.txt` and carry no system JRE, so we fall back to the
    pip-installed runtime from `jdk4py`. A system java, if present, wins —
    an operator who installed one meant it to be used.

    Returns:
        The path to the java binary that will be used, or None if the system
        one is already on PATH.
    """
    if shutil.which('java'):
        return None

    try:
        import jdk4py
    except ImportError:
        raise RuntimeError(
            'No Java runtime found. Open Data Loader needs a JRE 11+.\n'
            'Install one system-wide, or `pip install jdk4py` to get a '
            'self-contained runtime (it is in requirements.txt).'
        )

    java_bin = Path(jdk4py.JAVA)
    os.environ['JAVA_HOME'] = str(jdk4py.JAVA_HOME)
    os.environ['PATH'] = f'{java_bin.parent}{os.pathsep}' + os.environ.get('PATH', '')
    return java_bin


# Must run before opendataloader_pdf resolves `java` from PATH.
ensure_java_runtime()

import opendataloader_pdf  # noqa: E402  (import follows the java-path shim)

IMAGE_HEAVY_THRESHOLD = 30

# Emitted by Open Data Loader between pages; also the marker downstream
# steps (clean_md, inject_descriptions) key on.
PAGE_SEPARATOR_TEMPLATE = '<!-- page: %page-number% -->'
PAGE_SEPARATOR_RE = re.compile(r'^<!--\s*page:\s*(\d+)\s*-->\s*$', re.MULTILINE)

# Open Data Loader writes refs as ![](<path with spaces.png>). The angle
# brackets are legal CommonMark but break the plain !\[(.*?)\]\((.*?)\)
# regexes used by clean_md.py / inject_descriptions.py, so we normalise them.
IMAGE_REF_RE = re.compile(r'!\[([^\]]*)\]\(\s*<?([^)>]+)>?\s*\)')


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


def normalize_image_refs(md_text, base_dir, image_dir=None):
    """
    Rewrite Open Data Loader image references into the form downstream steps
    expect: ![alt](/absolute/path.png), with no angle brackets.

    The loader emits refs relative to its *output* dir, echoing only the last
    component of --image-dir (e.g. ![](<good/imageFile1.png>)) — so those paths
    do not resolve to where the files were actually written. Since the loader
    writes every image flat into --image-dir, we re-anchor each ref onto
    image_dir by basename.

    Args:
        md_text: Markdown emitted by Open Data Loader
        base_dir: Directory the emitted relative paths nominally resolve
                  against (the loader's output dir)
        image_dir: Directory the images were actually written to. When given,
                   refs are re-anchored here by filename.

    Returns:
        Markdown with every image reference rewritten to an absolute path.
    """
    base_dir = Path(base_dir)
    image_dir = Path(image_dir) if image_dir else None

    def _rewrite(match):
        alt, raw_path = match.group(1), match.group(2).strip()
        path = Path(raw_path)
        if image_dir is not None:
            path = image_dir / path.name
        elif not path.is_absolute():
            path = (base_dir / path).resolve()
        return f'![{alt}]({path})'

    return IMAGE_REF_RE.sub(_rewrite, md_text)


def split_pages(md_text):
    """
    Split loader markdown into pages on the page-separator comment.

    Returns:
        List of (page_num, page_text) tuples, 1-indexed. Content appearing
        before the first separator is attributed to page 1.
    """
    matches = list(PAGE_SEPARATOR_RE.finditer(md_text))

    if not matches:
        # No separators emitted (e.g. single-page doc) — treat as one page
        return [(1, md_text.strip())] if md_text.strip() else []

    pages = []

    # Any preamble before the first separator belongs to the first page
    preamble = md_text[:matches[0].start()].strip()

    for i, match in enumerate(matches):
        page_num = int(match.group(1))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        page_text = md_text[match.end():end].strip()

        if i == 0 and preamble:
            page_text = f'{preamble}\n\n{page_text}'.strip()

        pages.append((page_num, page_text))

    return pages


def run_open_data_loader(pdf_path, output_dir, image_dir=None):
    """
    Invoke Open Data Loader and return the markdown it produced.

    Args:
        pdf_path: Path to the source PDF
        output_dir: Directory the loader writes its .md into
        image_dir: If given, extract images as files into this directory

    Returns:
        The markdown text.

    Raises:
        RuntimeError: If the loader produced no markdown file.
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    kwargs = {
        'input_path': str(pdf_path),
        'output_dir': str(output_dir),
        'format': 'markdown',
        'quiet': True,
        'markdown_page_separator': PAGE_SEPARATOR_TEMPLATE,
    }

    if image_dir:
        # 'external' writes real image files; 'embedded' would inline base64
        # data URIs, which the dedup/vision steps cannot open.
        kwargs['image_output'] = 'external'
        kwargs['image_format'] = 'png'
        kwargs['image_dir'] = str(Path(image_dir))
    else:
        kwargs['image_output'] = 'off'

    opendataloader_pdf.convert(**kwargs)

    md_file = output_dir / f'{pdf_path.stem}.md'
    if not md_file.exists():
        # Fall back to whatever single .md landed there
        produced = list(output_dir.glob('*.md'))
        if not produced:
            raise RuntimeError(
                f'Open Data Loader produced no markdown for {pdf_path.name}'
            )
        md_file = produced[0]

    return md_file.read_text(encoding='utf-8')


def pdf_to_markdown(pdf_path, output_path, write_images=False, images_dir=None,
                    image_heavy_threshold=IMAGE_HEAVY_THRESHOLD):
    """
    Convert PDF to Markdown format using Open Data Loader with page-aware
    extraction.

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
        image_path = images_dir / pdf_path.stem
        image_path.mkdir(parents=True, exist_ok=True)
        print(f"  Images will be saved to: {image_path}")

    # Run the loader into a scratch dir so its output naming (<stem>.md) does
    # not constrain where the caller wants the markdown to land.
    with tempfile.TemporaryDirectory() as tmp_dir:
        md_text = run_open_data_loader(
            pdf_path,
            tmp_dir,
            image_dir=image_path if image_path else None,
        )
        # Re-anchor image refs onto the real images folder; the loader's own
        # paths point at a location that does not exist.
        md_text = normalize_image_refs(md_text, tmp_dir, image_dir=image_path)

    pages = split_pages(md_text)

    md_parts = []
    page_classification = {}

    for page_num, page_text in pages:
        page_type, word_count = classify_page(page_text, image_heavy_threshold)

        # Find images referenced in this page
        images_in_page = re.findall(r'!\[.*?\]\((.*?)\)', page_text)
        image_names = [Path(img).name for img in images_in_page]

        page_classification[str(page_num)] = {
            'type': page_type,
            'word_count': word_count,
            'images': image_names,
        }

        print(f"  Page {page_num}: {page_type} (words: {word_count}, images: {len(image_names)})")

        # Add page separator
        md_parts.append(f'<!-- page: {page_num} -->')

        if page_type == 'image_heavy':
            # Strip text artifacts, keep only image references
            # Pixtral will be the sole content source for this page
            md_parts.append(strip_text_keep_images(page_text))
        else:
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

Requires a JRE 11+ on PATH (Open Data Loader ships a bundled engine).
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
