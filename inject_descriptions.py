#!/usr/bin/env python3
"""
Inject Image Descriptions into Markdown
Replaces image references with text descriptions from JSON file
"""

import json
import re
import argparse
from pathlib import Path
from typing import Dict, Optional


def load_descriptions(json_file: str) -> Dict[str, str]:
    """
    Load image descriptions from JSON file
    
    Args:
        json_file: Path to descriptions JSON file
    
    Returns:
        Dict mapping image filenames to descriptions
    """
    json_path = Path(json_file)
    
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_file}")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        descriptions = json.load(f)
    
    return descriptions


def inject_descriptions(md_file: str, descriptions: Dict[str, str], 
                       output_file: Optional[str] = None,
                       format_style: str = 'blockquote') -> tuple[str, int]:
    """
    Replace image references with text descriptions
    
    Args:
        md_file: Path to markdown file
        descriptions: Dict of image filename -> description
        output_file: Output file path (default: overwrite original)
        format_style: How to format injected text ('blockquote', 'paragraph', 'section')
    
    Returns:
        Tuple: (modified_content, replacement_count)
    """
    md_path = Path(md_file)
    
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_file}")
    
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    replacement_count = 0
    
    # Pattern to match markdown images: ![alt](path)
    image_pattern = r'!\[([^\]]*)\]\(([^\)]+)\)'
    
    def replace_image(match):
        nonlocal replacement_count
        alt_text = match.group(1)
        image_path = match.group(2)
        image_filename = Path(image_path).name
        
        # Check if we have a description for this image
        if image_filename in descriptions:
            description = descriptions[image_filename]
            
            # Skip error entries
            if description.startswith('ERROR:'):
                print(f"  ⚠ Skipping {image_filename}: {description}")
                return match.group(0)
            
            replacement_count += 1
            
            # Format based on style
            if format_style == 'blockquote':
                # Use blockquote for clear separation
                return f'\n> **[Image: {image_filename}]**\n> {description}\n'
            
            elif format_style == 'paragraph':
                # Simple paragraph with bold header
                return f'\n**[Image: {image_filename}]**\n\n{description}\n'
            
            elif format_style == 'section':
                # Section with heading
                return f'\n#### Image: {image_filename}\n\n{description}\n'
            
            elif format_style == 'inline':
                # Inline without image filename
                return f' {description} '
            
            else:
                # Default to blockquote
                return f'\n> **[Image: {image_filename}]**\n> {description}\n'
        
        # Keep original if no description found
        return match.group(0)
    
    # Replace images with descriptions
    modified_content = re.sub(image_pattern, replace_image, content)
    
    # Clean up excessive blank lines
    modified_content = re.sub(r'\n{4,}', '\n\n\n', modified_content)
    
    # Write output
    if output_file:
        output_path = Path(output_file)
    else:
        output_path = md_path
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(modified_content)
    
    return modified_content, replacement_count


def process_folder(folder_path: str, descriptions_json: str, 
                  output_folder: Optional[str] = None,
                  format_style: str = 'blockquote') -> Dict[str, int]:
    """
    Process all markdown files in a folder
    
    Args:
        folder_path: Path to folder containing markdown files
        descriptions_json: Path to descriptions JSON file
        output_folder: Output folder (default: overwrite originals)
        format_style: How to format injected text
    
    Returns:
        Dict mapping filenames to replacement counts
    """
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")
    
    # Load descriptions
    descriptions = load_descriptions(descriptions_json)
    
    # Find all markdown files
    md_files = list(folder.glob("*.md"))
    
    if not md_files:
        print(f"No markdown files found in {folder}")
        return {}
    
    print(f"Found {len(md_files)} markdown file(s)")
    print(f"Loaded {len(descriptions)} image description(s)")
    print("-" * 60)
    
    results = {}
    
    for md_file in md_files:
        try:
            # Determine output path
            if output_folder:
                output_path = Path(output_folder) / md_file.name
            else:
                output_path = None
            
            print(f"Processing: {md_file.name}")
            _, count = inject_descriptions(str(md_file), descriptions, 
                                         output_file=str(output_path) if output_path else None,
                                         format_style=format_style)
            results[md_file.name] = count
            print(f"  ✓ Replaced {count} image(s)")
        
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results[md_file.name] = 0
    
    print("-" * 60)
    total = sum(results.values())
    print(f"Total replacements: {total}")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Replace image references with text descriptions in markdown files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Single file:
    python inject_descriptions.py document.md --descriptions descriptions.json
  
  Save to new file:
    python inject_descriptions.py document.md --descriptions descriptions.json --output clean_doc.md
  
  Process folder:
    python inject_descriptions.py --folder ./docs --descriptions descriptions.json
  
  Different formatting styles:
    python inject_descriptions.py document.md --descriptions descriptions.json --format paragraph
    python inject_descriptions.py document.md --descriptions descriptions.json --format section
    python inject_descriptions.py document.md --descriptions descriptions.json --format inline

Format styles:
  - blockquote: (default) Use '>' blockquote with bold header
  - paragraph: Bold header with paragraph
  - section: Use #### heading
  - inline: Plain text without image filename
        """
    )
    
    parser.add_argument('markdown', nargs='?', help='Input markdown file')
    parser.add_argument('--descriptions', required=True, help='Path to descriptions JSON file')
    parser.add_argument('--output', help='Output markdown file (default: overwrite original)')
    parser.add_argument('--folder', help='Process all .md files in folder')
    parser.add_argument('--output-folder', help='Output folder for processed files')
    parser.add_argument('--format', dest='format_style', 
                       choices=['blockquote', 'paragraph', 'section', 'inline'],
                       default='blockquote',
                       help='Format style for injected descriptions (default: blockquote)')
    
    args = parser.parse_args()
    
    try:
        # Process folder
        if args.folder:
            results = process_folder(args.folder, args.descriptions, 
                                   args.output_folder, args.format_style)
            
            if args.output_folder:
                print(f"\n✓ Files saved to: {args.output_folder}")
        
        # Process single file
        elif args.markdown:
            print(f"Processing: {args.markdown}")
            descriptions = load_descriptions(args.descriptions)
            print(f"Loaded {len(descriptions)} image description(s)")
            print("-" * 60)
            
            _, count = inject_descriptions(args.markdown, descriptions, 
                                         args.output, args.format_style)
            
            output_path = args.output if args.output else args.markdown
            print(f"✓ Saved to: {output_path}")
            print(f"✓ Replaced {count} image reference(s)")
        
        else:
            parser.print_help()
            import sys
            sys.exit(1)
    
    except Exception as e:
        print(f"Error: {e}")
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()