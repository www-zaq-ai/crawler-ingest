#!/usr/bin/env python3
"""
Image to Text using Scaleway Pixtral API
Processes images and extracts text descriptions for RAG applications
"""

import os
import sys
import json
import base64
import argparse
from pathlib import Path
from typing import List, Dict, Optional
import requests

DESCRIBE_PROMPT = """Describe this image concisely for document search and retrieval.
Focus only on actual content present: visible text, data in tables/charts,
diagrams, and meaningful visual elements. Skip introductions, explanations
about what's not in the image, and formatting descriptions. Be direct and factual."""

TRANSCRIBE_PROMPT = """You are processing a slide from a technical document for search indexing.
Extract ALL of the following if present:
1. Exact visible text (titles, labels, paragraph numbers like 4.6.8, section references)
2. Table contents (row by row)
3. Diagram description (what it shows, what the arrows/shapes mean)
4. Any standards references (EN XXXXX, ISO XXXXX, §X.X.X)

Be exhaustive with text transcription. Do not paraphrase visible text — copy it exactly."""


class PixtralImageProcessor:
    """Process images using Scaleway's Pixtral vision model"""
    
    def __init__(self, api_key: Optional[str] = None,
                 api_url: Optional[str] = None,
                 model: Optional[str] = None):
        """
        Initialize Pixtral processor

        Args:
            api_key: Scaleway API key (or set SCALEWAY_API_KEY env var)
            api_url: Override the default Scaleway API endpoint
            model: Override the default model name
        """
        self.api_key = api_key or os.getenv('SCALEWAY_API_KEY')
        if not self.api_key:
            raise ValueError("API key required. Set SCALEWAY_API_KEY or pass api_key parameter")

        # Scaleway Pixtral endpoint (overridable)
        self.api_url = api_url or "https://api.scaleway.ai/v1/chat/completions"
        self.model = model or "pixtral-12b-2409"
    
    @staticmethod
    def _make_1px_jpeg_b64() -> str:
        """Generate a 1x1 white JPEG in memory and return as base64."""
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new('RGB', (32, 32), (255, 255, 255)).save(buf, format='JPEG')
        return base64.b64encode(buf.getvalue()).decode()

    def ping(self) -> bool:
        """
        Verify API connectivity by sending a 1x1 pixel image.

        Returns:
            True if the API responds successfully, raises on failure.
        """
        pixel_b64 = self._make_1px_jpeg_b64()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Reply with OK."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{pixel_b64}"
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 50,
        }

        response = requests.post(self.api_url, headers=headers, json=payload)
        if not response.ok:
            raise ValueError(f"API error {response.status_code}: {response.text}")
        return True

    def encode_image(self, image_path: str) -> str:
        """
        Encode image to base64
        
        Args:
            image_path: Path to image file
        
        Returns:
            Base64 encoded image string
        """
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def clean_description(self, description: str) -> str:
        """
        Clean up verbose API responses
        
        Args:
            description: Raw description from API
        
        Returns:
            Cleaned, concise description
        """
        import re
        
        # Remove common fluff patterns
        fluff_patterns = [
            r'Certainly!?\s*',
            r'Below is a detailed description.*?:',
            r'### Main Content:',
            r'### Text Visible in the Image:',
            r'### Charts/Graphs Data:',
            r'### Diagrams:',
            r'### Key Visual Elements:',
            r'There are no charts or graphs present in the image\.',
            r'There are no diagrams present in the image\.',
            r'This concise yet comprehensive description.*',
            r'This (?:description )?should help.*',
            r'The image (?:displays|shows|contains)',
        ]
        
        cleaned = description
        for pattern in fluff_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove excessive newlines and whitespace
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        
        # Remove leading bullets/dashes if they're just list markers
        lines = cleaned.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line.startswith('- **') or line.startswith('* **'):
                # Keep structured data like "- **Field:** Value"
                cleaned_lines.append(line)
            elif line.startswith(('- ', '* ')):
                # Remove simple bullet markers
                cleaned_lines.append(line[2:].strip())
            elif line:
                cleaned_lines.append(line)
        
        cleaned = '\n'.join(cleaned_lines).strip()
        
        return cleaned
    
    def get_image_description(self, image_path: str, prompt: Optional[str] = None, 
                             clean: bool = True) -> str:
        """
        Get text description of an image
        
        Args:
            image_path: Path to image file
            prompt: Custom prompt (default: describe image for RAG)
            clean: Apply post-processing to remove verbose fluff
        
        Returns:
            Text description of the image
        """
        if not Path(image_path).exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # Default RAG-optimized prompt
        if not prompt:
            prompt = DESCRIBE_PROMPT
        
        # Encode image
        base64_image = self.encode_image(image_path)
        
        # Prepare request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 500
        }
        
        # Make request
        response = requests.post(self.api_url, headers=headers, json=payload)
        response.raise_for_status()
        
        result = response.json()
        description = result['choices'][0]['message']['content']
        
        # Clean if requested
        if clean:
            description = self.clean_description(description)
        
        return description.strip()
    
    def _load_image_heavy_set(self, page_classification_path: Optional[str]) -> set:
        """
        Load set of image filenames that belong to image-heavy pages.

        Args:
            page_classification_path: Path to page_classification.json from pdf_to_md.py

        Returns:
            Set of image filenames that should use the transcribe prompt
        """
        if not page_classification_path:
            return set()

        classification_file = Path(page_classification_path)
        if not classification_file.exists():
            print(f"⚠ Page classification not found: {classification_file}")
            return set()

        with open(classification_file, 'r', encoding='utf-8') as f:
            classification = json.load(f)

        image_heavy_images = set()
        for page_info in classification.values():
            if page_info.get('type') == 'image_heavy':
                image_heavy_images.update(page_info.get('images', []))

        if image_heavy_images:
            print(f"  {len(image_heavy_images)} image(s) from image-heavy pages will use transcribe prompt")

        return image_heavy_images

    def process_folder(self, folder_path: str, output_file: Optional[str] = None,
                      prompt: Optional[str] = None, clean: bool = True,
                      prompt_mode: str = 'describe',
                      page_classification_path: Optional[str] = None) -> Dict[str, str]:
        """
        Process all images in a folder

        Args:
            folder_path: Path to folder containing images
            output_file: Path to save results (JSON format)
            prompt: Custom prompt for all images (overrides prompt_mode)
            clean: Apply post-processing to clean responses
            prompt_mode: 'describe' (default) or 'transcribe' — used when no custom prompt
            page_classification_path: Path to page_classification.json for per-image
                                     prompt selection (image-heavy pages get transcribe)

        Returns:
            Dict mapping image filenames to descriptions
        """
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder}")

        # Supported image extensions
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

        # Find all images
        image_files = []
        for ext in image_extensions:
            image_files.extend(folder.glob(f"*{ext}"))
            image_files.extend(folder.glob(f"*{ext.upper()}"))

        if not image_files:
            print(f"No images found in {folder}")
            return {}

        print(f"Found {len(image_files)} image(s)")

        # Load page classification for per-image prompt selection
        image_heavy_set = self._load_image_heavy_set(page_classification_path)

        # Determine default prompt based on mode
        if not prompt:
            default_prompt = TRANSCRIBE_PROMPT if prompt_mode == 'transcribe' else DESCRIBE_PROMPT
        else:
            default_prompt = prompt

        print("-" * 60)

        results = {}

        for idx, img_path in enumerate(image_files, 1):
            try:
                # Use transcribe prompt for images from image-heavy pages
                if img_path.name in image_heavy_set:
                    img_prompt = TRANSCRIBE_PROMPT
                    mode_label = "transcribe"
                else:
                    img_prompt = default_prompt
                    mode_label = prompt_mode if not prompt else "custom"

                print(f"[{idx}/{len(image_files)}] Processing: {img_path.name} ({mode_label})")
                description = self.get_image_description(str(img_path), img_prompt, clean=clean)
                results[img_path.name] = description
                print(f"  ✓ Done")
            except Exception as e:
                print(f"  ✗ Error: {e}")
                results[img_path.name] = f"ERROR: {str(e)}"

        print("-" * 60)
        print(f"Completed: {len([v for v in results.values() if not v.startswith('ERROR')])}/{len(image_files)}")

        # Save results
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

            print(f"✓ Results saved to: {output_path}")

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Extract text descriptions from images using Scaleway Pixtral",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Process single image:
    python image_to_text.py image.png
  
  Process folder of images:
    python image_to_text.py --folder ./images/report
  
  Save results to JSON:
    python image_to_text.py --folder ./images/report --output descriptions.json
  
  Custom prompt:
    python image_to_text.py --folder ./images --output results.json --prompt "Extract all text from this image"

Environment:
  Set SCALEWAY_API_KEY environment variable with your API key
        """
    )
    
    parser.add_argument('image', nargs='?', help='Single image file to process')
    parser.add_argument('--folder', help='Folder containing images to process')
    parser.add_argument('--output', help='Output JSON file for results')
    parser.add_argument('--prompt', help='Custom prompt for image description (overrides --prompt-mode)')
    parser.add_argument('--prompt-mode', choices=['describe', 'transcribe'], default='describe',
                       help='Prompt mode: describe (default, good for photos/diagrams) or '
                            'transcribe (extract exact text + structure, good for slides)')
    parser.add_argument('--page-classification', help='Path to page_classification.json from pdf_to_md.py '
                       '(auto-selects transcribe for image-heavy page images)')
    parser.add_argument('--api-key', help='Scaleway API key (or set SCALEWAY_API_KEY env var)')
    parser.add_argument('--api-url', help='Override the default Scaleway API endpoint URL')
    parser.add_argument('--model', help='Override the default model name (default: pixtral-12b-2409)')
    parser.add_argument('--no-clean', action='store_true', help='Skip post-processing cleanup of responses')
    parser.add_argument('--ping', action='store_true', help='Send a 1-pixel image to verify API connectivity and exit')

    args = parser.parse_args()

    try:
        # Initialize processor
        processor = PixtralImageProcessor(
            api_key=args.api_key,
            api_url=args.api_url,
            model=args.model,
        )

        # Ping
        if args.ping:
            processor.ping()
            print("OK")
            sys.exit(0)

        # Process folder
        if args.folder:
            results = processor.process_folder(args.folder, args.output, args.prompt,
                                             clean=not args.no_clean,
                                             prompt_mode=args.prompt_mode,
                                             page_classification_path=args.page_classification)
            
            # Display sample results
            if results:
                print("\nSample descriptions:")
                print("=" * 60)
                for img_name, desc in list(results.items())[:3]:
                    print(f"\n{img_name}:")
                    print(desc[:200] + "..." if len(desc) > 200 else desc)
        
        # Process single image
        elif args.image:
            print(f"Processing: {args.image}")
            description = processor.get_image_description(args.image, args.prompt, 
                                                        clean=not args.no_clean)
            
            print("\nDescription:")
            print("=" * 60)
            print(description)
            
            # Save if output specified
            if args.output:
                output_path = Path(args.output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump({Path(args.image).name: description}, f, indent=2, ensure_ascii=False)
                
                print(f"\n✓ Saved to: {args.output}")
        
        else:
            parser.print_help()
            sys.exit(1)
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()