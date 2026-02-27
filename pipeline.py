#!/usr/bin/env python3
"""
PDF to Clean Markdown Pipeline
Complete workflow: Extract PDF -> Remove duplicate images -> Get descriptions -> Clean markdown
"""

import sys
import argparse
import subprocess
from pathlib import Path
from typing import Optional
import json


class PDFPipeline:
    """Orchestrate the complete PDF processing pipeline"""
    
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.python = sys.executable
        script_dir = Path(__file__).resolve().parent
        self.scripts = {
            'pdf_to_md': str(script_dir / 'pdf_to_md.py'),
            'image_dedup': str(script_dir / 'image_dedup.py'),
            'image_to_text': str(script_dir / 'image_to_text.py'),
            'clean_md': str(script_dir / 'clean_md.py'),
            'inject_descriptions': str(script_dir / 'inject_descriptions.py')
        }
    
    def log(self, message: str):
        """Print log message if verbose"""
        if self.verbose:
            print(message)
    
    def run_command(self, cmd: list, step_name: str) -> bool:
        """
        Run a command and handle errors
        
        Args:
            cmd: Command to run as list
            step_name: Name of the step for logging
        
        Returns:
            True if successful, False otherwise
        """
        self.log(f"\n{'='*60}")
        self.log(f"STEP: {step_name}")
        self.log(f"{'='*60}")
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            if self.verbose and result.stdout:
                print(result.stdout)
            return True
        except subprocess.CalledProcessError as e:
            print(f"✗ Error in {step_name}:")
            print(e.stderr)
            return False
    
    def process_single_pdf(self, pdf_path: str, output_md: Optional[str] = None,
                          images_dir: str = './images',
                          api_key: Optional[str] = None,
                          threshold: int = 5,
                          format_style: str = 'blockquote',
                          keep_duplicates: bool = False) -> bool:
        """
        Process a single PDF through the complete pipeline
        
        Args:
            pdf_path: Path to PDF file
            output_md: Output markdown path (default: same name as PDF)
            images_dir: Base directory for images
            api_key: Scaleway API key
            threshold: Image similarity threshold
            format_style: Description format style
            keep_duplicates: Keep duplicate images (don't delete)
        
        Returns:
            True if successful
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            print(f"✗ PDF file not found: {pdf_path}")
            return False
        
        # Determine output paths
        if not output_md:
            output_md = pdf_path.with_suffix('.md')
        else:
            output_md = Path(output_md)
        
        pdf_name = pdf_path.stem
        images_folder = Path(images_dir) / pdf_name
        descriptions_json = images_folder / 'descriptions.json'
        duplicate_mapping = images_folder / 'duplicate_mapping.txt'
        
        self.log(f"\n{'#'*60}")
        self.log(f"Processing: {pdf_path.name}")
        self.log(f"Output: {output_md}")
        self.log(f"Images: {images_folder}")
        self.log(f"{'#'*60}")
        
        # Step 1: Extract PDF with images
        cmd = [
            self.python, self.scripts['pdf_to_md'],
            str(pdf_path), str(output_md),
            '--with-images', '--images-dir', str(images_dir)
        ]
        if not self.run_command(cmd, "1. Extract PDF with images"):
            return False
        
        # Check if images were extracted
        if not images_folder.exists() or not list(images_folder.glob('*.png')):
            self.log("\n⚠ No images extracted, skipping image processing steps")
            self.log(f"\n✓ Markdown saved to: {output_md}")
            return True
        
        # Step 2: Remove duplicate images
        cmd = [
            self.python, self.scripts['image_dedup'],
            str(images_folder),
            '--threshold', str(threshold)
        ]
        if not keep_duplicates:
            cmd.append('--delete')
        
        if not self.run_command(cmd, "2. Detect and remove duplicate images"):
            return False
        
        # Check if duplicate mapping exists (only if duplicates were found)
        if not duplicate_mapping.exists():
            self.log("\n⚠ No duplicate mapping found, skipping clean step")
            has_duplicates = False
        else:
            has_duplicates = True
        
        # Step 3: Get image descriptions with Pixtral
        cmd = [
            self.python, self.scripts['image_to_text'],
            '--folder', str(images_folder),
            '--output', str(descriptions_json)
        ]
        if api_key:
            cmd.extend(['--api-key', api_key])
        
        if not self.run_command(cmd, "3. Extract text from images (Pixtral)"):
            return False
        
        # Step 4: Clean markdown (remove duplicate image references)
        if has_duplicates:
            cmd = [
                self.python, self.scripts['clean_md'],
                str(output_md),
                '--mapping', str(duplicate_mapping)
            ]
            if not self.run_command(cmd, "4. Clean markdown (remove duplicates)"):
                return False
        else:
            self.log("\n{'='*60}")
            self.log("STEP: 4. Clean markdown (remove duplicates)")
            self.log("{'='*60}")
            self.log("⚠ Skipping - no duplicates found")
        
        # Step 5: Inject image descriptions
        cmd = [
            self.python, self.scripts['inject_descriptions'],
            str(output_md),
            '--descriptions', str(descriptions_json),
            '--format', format_style
        ]
        if not self.run_command(cmd, "5. Inject image descriptions"):
            return False
        
        # Final summary
        self.log(f"\n{'#'*60}")
        self.log("✓ PIPELINE COMPLETED SUCCESSFULLY")
        self.log(f"{'#'*60}")
        self.log(f"📄 Clean markdown: {output_md}")
        self.log(f"🖼️  Images: {images_folder}")
        self.log(f"📝 Descriptions: {descriptions_json}")
        if has_duplicates:
            self.log(f"🔍 Duplicate mapping: {duplicate_mapping}")
        
        return True
    
    def process_folder(self, input_folder: str, output_folder: str,
                      images_dir: str = './images',
                      api_key: Optional[str] = None,
                      threshold: int = 5,
                      format_style: str = 'blockquote',
                      keep_duplicates: bool = False) -> dict:
        """
        Process all PDFs in a folder
        
        Args:
            input_folder: Folder containing PDF files
            output_folder: Folder for output markdown files
            images_dir: Base directory for images
            api_key: Scaleway API key
            threshold: Image similarity threshold
            format_style: Description format style
            keep_duplicates: Keep duplicate images
        
        Returns:
            Dict with processing results
        """
        input_path = Path(input_folder)
        output_path = Path(output_folder)
        
        if not input_path.exists():
            print(f"✗ Input folder not found: {input_folder}")
            return {}
        
        # Find all PDFs
        pdf_files = list(input_path.glob('*.pdf'))
        
        if not pdf_files:
            print(f"✗ No PDF files found in {input_folder}")
            return {}
        
        output_path.mkdir(parents=True, exist_ok=True)
        
        self.log(f"\nFound {len(pdf_files)} PDF file(s)")
        self.log(f"Output folder: {output_path}")
        
        results = {}
        success_count = 0
        
        for idx, pdf_file in enumerate(pdf_files, 1):
            self.log(f"\n\n{'█'*60}")
            self.log(f"PROCESSING {idx}/{len(pdf_files)}: {pdf_file.name}")
            self.log(f"{'█'*60}")
            
            output_md = output_path / pdf_file.with_suffix('.md').name
            
            success = self.process_single_pdf(
                str(pdf_file),
                str(output_md),
                images_dir=images_dir,
                api_key=api_key,
                threshold=threshold,
                format_style=format_style,
                keep_duplicates=keep_duplicates
            )
            
            results[pdf_file.name] = success
            if success:
                success_count += 1
        
        # Final summary
        self.log(f"\n\n{'█'*60}")
        self.log(f"BATCH PROCESSING COMPLETE")
        self.log(f"{'█'*60}")
        self.log(f"Success: {success_count}/{len(pdf_files)}")
        self.log(f"Failed: {len(pdf_files) - success_count}/{len(pdf_files)}")
        
        return results


def main():
    parser = argparse.ArgumentParser(
        description="Complete PDF to Clean Markdown Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Single PDF:
    python pipeline.py report.pdf
  
  Single PDF with custom output:
    python pipeline.py report.pdf --output clean_report.md
  
  Batch process folder:
    python pipeline.py --input-folder ./pdfs --output-folder ./markdown
  
  With custom settings:
    python pipeline.py report.pdf --images-dir ./my_images --threshold 3 --format paragraph
  
  Keep duplicate images (don't delete):
    python pipeline.py report.pdf --keep-duplicates

Environment:
  Set SCALEWAY_API_KEY environment variable with your API key
        """
    )
    
    parser.add_argument('pdf', nargs='?', help='Input PDF file')
    parser.add_argument('--output', help='Output markdown file')
    parser.add_argument('--input-folder', help='Folder containing PDF files')
    parser.add_argument('--output-folder', help='Folder for output markdown files')
    parser.add_argument('--images-dir', default='./images', 
                       help='Base directory for images (default: ./images)')
    parser.add_argument('--api-key', help='Scaleway API key (or set SCALEWAY_API_KEY env var)')
    parser.add_argument('--threshold', type=int, default=5,
                       help='Image similarity threshold (default: 5)')
    parser.add_argument('--format', dest='format_style',
                       choices=['blockquote', 'paragraph', 'section', 'inline'],
                       default='blockquote',
                       help='Description format style (default: blockquote)')
    parser.add_argument('--keep-duplicates', action='store_true',
                       help='Keep duplicate images (don\'t delete them)')
    parser.add_argument('--quiet', action='store_true',
                       help='Suppress verbose output')
    
    args = parser.parse_args()
    
    try:
        pipeline = PDFPipeline(verbose=not args.quiet)
        
        # Batch processing
        if args.input_folder and args.output_folder:
            results = pipeline.process_folder(
                args.input_folder,
                args.output_folder,
                images_dir=args.images_dir,
                api_key=args.api_key,
                threshold=args.threshold,
                format_style=args.format_style,
                keep_duplicates=args.keep_duplicates
            )
            
            # Check if any failed
            failed = [k for k, v in results.items() if not v]
            if failed:
                print(f"\n⚠ Some files failed: {', '.join(failed)}")
                sys.exit(1)
        
        # Single file processing
        elif args.pdf:
            success = pipeline.process_single_pdf(
                args.pdf,
                output_md=args.output,
                images_dir=args.images_dir,
                api_key=args.api_key,
                threshold=args.threshold,
                format_style=args.format_style,
                keep_duplicates=args.keep_duplicates
            )
            
            if not success:
                sys.exit(1)
        
        else:
            parser.print_help()
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n\n⚠ Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Pipeline error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()