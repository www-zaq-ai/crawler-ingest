#!/usr/bin/env python3
"""
Clean Markdown Files - Remove Duplicate Image References
Uses duplicate_mapping.txt to remove duplicate image references from markdown files
"""

import re
import argparse
from pathlib import Path


def load_duplicate_mapping(mapping_file):
    """
    Load duplicate mapping from text file
    
    Args:
        mapping_file: Path to duplicate_mapping.txt
    
    Returns:
        Dict mapping duplicate filenames -> original filenames
    """
    mapping = {}
    mapping_path = Path(mapping_file)
    
    if not mapping_path.exists():
        raise FileNotFoundError(f"Mapping file not found: {mapping_file}")
    
    with open(mapping_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            # Parse "duplicate -> original" format
            if '->' in line:
                parts = line.split('->')
                if len(parts) == 2:
                    duplicate = Path(parts[0].strip()).name
                    original = Path(parts[1].strip()).name
                    mapping[duplicate] = original
    
    return mapping


def clean_markdown(md_file, duplicate_mapping, output_file=None, remove_duplicates=True):
    """
    Clean markdown file by removing or replacing duplicate image references
    
    Args:
        md_file: Path to markdown file
        duplicate_mapping: Dict of duplicate -> original filenames
        output_file: Output file path (default: overwrite original)
        remove_duplicates: If True, remove duplicates. If False, replace with original
    
    Returns:
        Tuple: (cleaned_content, removed_count, replaced_count)
    """
    md_path = Path(md_file)
    
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_file}")
    
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    removed_count = 0
    replaced_count = 0
    
    # Pattern to match markdown images: ![alt](path)
    image_pattern = r'!\[([^\]]*)\]\(([^\)]+)\)'
    
    def replace_image(match):
        nonlocal removed_count, replaced_count
        alt_text = match.group(1)
        image_path = match.group(2)
        image_filename = Path(image_path).name
        
        # Check if this image is a duplicate
        if image_filename in duplicate_mapping:
            if remove_duplicates:
                # Remove the entire image reference
                removed_count += 1
                return ''
            else:
                # Replace with original image reference
                original = duplicate_mapping[image_filename]
                original_path = image_path.replace(image_filename, original)
                replaced_count += 1
                return f'![{alt_text}]({original_path})'
        
        # Keep original if not a duplicate
        return match.group(0)
    
    # Replace/remove duplicate images
    cleaned_content = re.sub(image_pattern, replace_image, content)
    
    # Remove excessive blank lines (more than 2 consecutive)
    cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)
    
    # Write output
    if output_file:
        output_path = Path(output_file)
    else:
        output_path = md_path
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(cleaned_content)
    
    return cleaned_content, removed_count, replaced_count


def main():
    parser = argparse.ArgumentParser(
        description="Clean markdown files by removing duplicate image references",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Remove duplicate images from markdown:
    python clean_md.py document.md --mapping images/duplicate_mapping.txt
  
  Replace duplicates with original (keep one reference):
    python clean_md.py document.md --mapping images/duplicate_mapping.txt --replace
  
  Save to new file:
    python clean_md.py document.md --mapping images/duplicate_mapping.txt --output cleaned.md
  
  Process all markdown files in a folder:
    python clean_md.py --input-folder ./docs --mapping images/duplicate_mapping.txt
        """
    )
    
    parser.add_argument('markdown', nargs='?', help='Input markdown file')
    parser.add_argument('--mapping', required=True, help='Path to duplicate_mapping.txt file')
    parser.add_argument('--output', help='Output markdown file (default: overwrite original)')
    parser.add_argument('--replace', action='store_true', 
                       help='Replace duplicates with original instead of removing')
    parser.add_argument('--input-folder', help='Process all .md files in folder')
    
    args = parser.parse_args()
    
    try:
        # Load mapping
        print(f"Loading duplicate mapping from: {args.mapping}")
        duplicate_mapping = load_duplicate_mapping(args.mapping)
        print(f"Found {len(duplicate_mapping)} duplicate mappings")
        print("-" * 60)
        
        # Process folder
        if args.input_folder:
            folder = Path(args.input_folder)
            if not folder.exists():
                raise FileNotFoundError(f"Folder not found: {folder}")
            
            md_files = list(folder.glob("*.md"))
            if not md_files:
                print(f"No markdown files found in {folder}")
                return
            
            print(f"Found {len(md_files)} markdown file(s)")
            print("-" * 60)
            
            total_removed = 0
            total_replaced = 0
            
            for md_file in md_files:
                print(f"\nProcessing: {md_file.name}")
                _, removed, replaced = clean_markdown(
                    md_file, 
                    duplicate_mapping, 
                    remove_duplicates=not args.replace
                )
                
                if args.replace:
                    print(f"  ✓ Replaced {replaced} duplicate reference(s)")
                    total_replaced += replaced
                else:
                    print(f"  ✓ Removed {removed} duplicate reference(s)")
                    total_removed += removed
            
            print("-" * 60)
            if args.replace:
                print(f"Total replaced: {total_replaced}")
            else:
                print(f"Total removed: {total_removed}")
        
        # Process single file
        elif args.markdown:
            print(f"Processing: {args.markdown}")
            _, removed, replaced = clean_markdown(
                args.markdown, 
                duplicate_mapping,
                output_file=args.output,
                remove_duplicates=not args.replace
            )
            
            output_path = args.output if args.output else args.markdown
            print(f"✓ Saved to: {output_path}")
            
            if args.replace:
                print(f"✓ Replaced {replaced} duplicate reference(s)")
            else:
                print(f"✓ Removed {removed} duplicate reference(s)")
        
        else:
            parser.print_help()
    
    except Exception as e:
        print(f"Error: {e}")
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()