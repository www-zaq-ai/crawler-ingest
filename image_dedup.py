#!/usr/bin/env python3
"""
Image Deduplication Module
Detects and removes duplicate images using perceptual hashing
Useful for removing repeated headers/footers in PDF extractions
"""

import imagehash
from PIL import Image
import io
from pathlib import Path
from typing import List, Set, Tuple


def get_image_hash(img_data, hash_size=8):
    """
    Generate perceptual hash for an image
    
    Args:
        img_data: Image as bytes or PIL Image object
        hash_size: Hash size (default: 8, larger = more precise)
    
    Returns:
        imagehash.ImageHash object
    """
    if isinstance(img_data, bytes):
        img = Image.open(io.BytesIO(img_data))
    else:
        img = img_data
    
    return imagehash.average_hash(img, hash_size=hash_size)


def are_images_similar(img1_data, img2_data, threshold=5, hash_size=8):
    """
    Check if two images are visually similar
    
    Args:
        img1_data: First image (bytes or PIL Image)
        img2_data: Second image (bytes or PIL Image)
        threshold: Hamming distance threshold (0=identical, 5=very similar, 10+=different)
        hash_size: Hash size for comparison
    
    Returns:
        bool: True if images are similar
    """
    hash1 = get_image_hash(img1_data, hash_size)
    hash2 = get_image_hash(img2_data, hash_size)
    
    distance = hash1 - hash2
    return distance <= threshold


def deduplicate_images(image_list, threshold=5, hash_size=8):
    """
    Remove duplicate images from a list
    
    Args:
        image_list: List of image data (bytes or PIL Images)
        threshold: Similarity threshold
        hash_size: Hash size for comparison
    
    Returns:
        Tuple: (unique_images, duplicate_indices)
            - unique_images: List of unique images
            - duplicate_indices: List of indices that were removed
    """
    if not image_list:
        return [], []
    
    unique_images = []
    seen_hashes = []
    duplicate_indices = []
    
    for idx, img_data in enumerate(image_list):
        img_hash = get_image_hash(img_data, hash_size)
        
        # Check if similar to any seen hash
        is_duplicate = False
        for seen_hash in seen_hashes:
            if img_hash - seen_hash <= threshold:
                is_duplicate = True
                break
        
        if is_duplicate:
            duplicate_indices.append(idx)
        else:
            unique_images.append(img_data)
            seen_hashes.append(img_hash)
    
    return unique_images, duplicate_indices


def deduplicate_image_files(image_paths, threshold=5, hash_size=8):
    """
    Remove duplicate images from a list of file paths
    
    Args:
        image_paths: List of image file paths
        threshold: Similarity threshold
        hash_size: Hash size for comparison
    
    Returns:
        Tuple: (unique_paths, duplicate_mapping)
            - unique_paths: List of unique image paths
            - duplicate_mapping: Dict mapping duplicate path -> original path
    """
    if not image_paths:
        return [], {}
    
    unique_paths = []
    seen_hashes = {}  # hash -> original file path
    duplicate_mapping = {}  # duplicate path -> original path
    
    for img_path in image_paths:
        try:
            with Image.open(img_path) as img:
                img_hash = get_image_hash(img, hash_size)
            
            # Check if similar to any seen hash
            original_file = None
            for seen_hash, seen_path in seen_hashes.items():
                if img_hash - seen_hash <= threshold:
                    original_file = seen_path
                    break
            
            if original_file:
                duplicate_mapping[str(img_path)] = str(original_file)
            else:
                unique_paths.append(img_path)
                seen_hashes[img_hash] = img_path
        except Exception as e:
            print(f"Warning: Could not process {img_path}: {e}")
            continue
    
    return unique_paths, duplicate_mapping


def save_duplicate_mapping(duplicate_mapping, output_file):
    """
    Save duplicate mapping to a text file
    
    Args:
        duplicate_mapping: Dict mapping duplicate -> original
        output_file: Path to output text file
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Image Duplicate Mapping\n")
        f.write("# Format: DUPLICATE_IMAGE -> ORIGINAL_IMAGE\n")
        f.write(f"# Total duplicates: {len(duplicate_mapping)}\n")
        f.write("#" + "=" * 70 + "\n\n")
        
        for duplicate, original in sorted(duplicate_mapping.items()):
            f.write(f"{duplicate} -> {original}\n")
    
    print(f"✓ Duplicate mapping saved to: {output_path}")
    return output_path


def process_image_folder(folder_path, threshold=5, hash_size=8, delete_duplicates=False, save_mapping=True):
    """
    Process all images in a folder and find duplicates
    
    Args:
        folder_path: Path to folder containing images
        threshold: Similarity threshold
        hash_size: Hash size for comparison
        delete_duplicates: If True, delete duplicate files
        save_mapping: If True, save duplicate mapping to text file
    
    Returns:
        Tuple: (unique_count, duplicate_count, duplicate_mapping)
    """
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")
    
    # Supported image extensions
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
    
    # Find all image files
    image_files = []
    for ext in image_extensions:
        image_files.extend(folder.glob(f"*{ext}"))
        image_files.extend(folder.glob(f"*{ext.upper()}"))
    
    if not image_files:
        print(f"No images found in {folder}")
        return 0, 0, {}
    
    print(f"Found {len(image_files)} image(s) in {folder}")
    print(f"Analyzing with threshold={threshold}...")
    print("-" * 60)
    
    # Deduplicate
    unique_paths, duplicate_mapping = deduplicate_image_files(
        image_files, 
        threshold=threshold, 
        hash_size=hash_size
    )
    
    # Display results
    print(f"\n✓ Unique images: {len(unique_paths)}")
    print(f"✗ Duplicate images: {len(duplicate_mapping)}")
    
    if duplicate_mapping:
        print("\nDuplicate files:")
        for dup_path, orig_path in list(duplicate_mapping.items())[:10]:
            dup_name = Path(dup_path).name
            orig_name = Path(orig_path).name
            print(f"  - {dup_name} -> {orig_name}")
        
        if len(duplicate_mapping) > 10:
            print(f"  ... and {len(duplicate_mapping) - 10} more")
        
        # Save mapping file
        if save_mapping:
            mapping_file = folder / "duplicate_mapping.txt"
            save_duplicate_mapping(duplicate_mapping, mapping_file)
        
        if delete_duplicates:
            print("\nDeleting duplicates...")
            deleted = 0
            for dup_path in duplicate_mapping.keys():
                try:
                    Path(dup_path).unlink()
                    deleted += 1
                    print(f"  ✓ Deleted: {Path(dup_path).name}")
                except Exception as e:
                    print(f"  ✗ Error deleting {Path(dup_path).name}: {e}")
            print(f"\n✓ Deleted {deleted} duplicate(s)")
    else:
        print("\n✓ No duplicates found!")
    
    return len(unique_paths), len(duplicate_mapping), duplicate_mapping


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Detect and remove duplicate images in a folder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Check for duplicates:
    python image_dedup.py /path/to/images
  
  Check with custom threshold:
    python image_dedup.py /path/to/images --threshold 3
  
  Delete duplicates automatically:
    python image_dedup.py /path/to/images --delete
        """
    )
    
    parser.add_argument('folder', help='Path to folder containing images')
    parser.add_argument(
        '--threshold', 
        type=int, 
        default=5,
        help='Similarity threshold (0=identical, 5=very similar, 10+=different)'
    )
    parser.add_argument(
        '--hash-size',
        type=int,
        default=8,
        help='Hash size for comparison (default: 8)'
    )
    parser.add_argument(
        '--delete',
        action='store_true',
        help='Delete duplicate files (use with caution!)'
    )
    
    args = parser.parse_args()
    
    try:
        process_image_folder(
            args.folder,
            threshold=args.threshold,
            hash_size=args.hash_size,
            delete_duplicates=args.delete
        )
    except Exception as e:
        print(f"Error: {e}")
        import sys
        sys.exit(1)