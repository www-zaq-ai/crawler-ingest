#!/usr/bin/env python3
"""
PDF to Markdown Converter using PyMuPDF4LLM
Extracts text, tables, and images from PDF files with proper formatting
Optimized for RAG/LLM applications
"""

import pymupdf4llm
import sys
import argparse
from pathlib import Path


def pdf_to_markdown(pdf_path, output_path, write_images=False, images_dir=None):
    """
    Convert PDF to Markdown format using pymupdf4llm
    
    Args:
        pdf_path: Path to input PDF file
        output_path: Path to output MD file
        write_images: Extract and save images separately (default: False)
        images_dir: Base directory for images. Will create subfolder named after PDF
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
    
    # Convert PDF to markdown
    md_text = pymupdf4llm.to_markdown(
        str(pdf_path),
        write_images=write_images,
        image_path=str(image_path) if image_path else None
    )
    
    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to markdown file
    output_path.write_bytes(md_text.encode())
    
    print(f"✓ Saved to: {output_path}")
    if image_path:
        print(f"✓ Images saved to: {image_path}")
    
    return output_path


def process_folder(input_folder, output_folder, write_images=False, images_dir=None):
    """
    Process all PDF files in a folder
    
    Args:
        input_folder: Path to folder containing PDF files
        output_folder: Path to folder for output MD files
        write_images: Extract and save images separately
        images_dir: Base directory for images (each PDF gets its own subfolder)
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
            pdf_to_markdown(pdf_file, output_file, write_images=write_images, images_dir=images_dir)
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
    
    args = parser.parse_args()
    
    try:
        # Batch processing mode
        if args.input_folder and args.output_folder:
            process_folder(args.input_folder, args.output_folder, args.with_images, args.images_dir)
        
        # Single file mode
        elif args.input:
            if not args.output:
                output = Path(args.input).with_suffix('.md')
            else:
                output = args.output
            pdf_to_markdown(args.input, output, args.with_images, args.images_dir)
        
        else:
            parser.print_help()
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()