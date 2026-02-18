# 📄 crawler-ingest

A pipeline that converts PDFs into clean, vector-DB-ready markdown — extracting images, deduplicating them, generating text descriptions via AI, and injecting everything back into polished documents.

---

## ✨ Features

- **PDF → Markdown** conversion with image extraction
- **Image deduplication** using perceptual hashing
- **AI-powered image descriptions** via Pixtral API
- **Automated cleanup** of duplicate references in markdown
- **Full pipeline** mode for one-command processing

---

## 🚀 Quick Start

Run the full pipeline with a single command:

```bash
python pipeline.py report.pdf
```

That's it. The pipeline handles extraction, deduplication, description generation, cleanup, and injection automatically.

**Output:**
```
clean_report.md          # Final markdown ready for vector DB
images/report/           # Unique images only
  descriptions.json      # All image descriptions
  duplicate_mapping.txt  # Record of what was removed
```

---

## 📖 Pipeline Overview

| Step | Script | What it does |
|------|--------|--------------|
| 1 | `pdf_to_md.py` | Extracts markdown and images from PDFs |
| 2 | `image_dedup.py` | Finds and removes duplicate images |
| 3 | `clean_md.py` | Removes or replaces duplicate image references |
| 4 | `image_to_text.py` | Generates AI descriptions for each image |
| 5 | `inject_descriptions.py` | Replaces image tags with text descriptions |

---

## 🔧 Step-by-Step Usage

If you prefer running each step manually, here's how.

### Step 1 — Extract PDF to Markdown

```bash
python pdf_to_md.py \
  --input-folder ./new_files \
  --output-folder ./new_output_files \
  --with-images \
  --images-dir ./new_images
```

### Step 2 — Deduplicate Images

Scan for duplicate images and generate a mapping file:

```bash
python image_dedup.py new_images/your_document_folder
```

Review the generated `duplicate_mapping.txt`, then delete duplicates:

```bash
python image_dedup.py new_images/your_document_folder --delete
```

The mapping file follows this format:

```
# Image Duplicate Mapping
# Format: DUPLICATE_IMAGE -> ORIGINAL_IMAGE

new_images/doc/doc.pdf-0-2.png -> new_images/doc/doc.pdf-1-1.png
new_images/doc/doc.pdf-10-0.png -> new_images/doc/doc.pdf-3-0.png
```

### Step 3 — Clean Markdown References

Remove duplicate image references from markdown, or replace them with the original:

```bash
# Remove all duplicate image references
python clean_md.py report.md --mapping ./images/report/duplicate_mapping.txt

# OR replace duplicates with the original reference
python clean_md.py report.md --mapping ./images/report/duplicate_mapping.txt --replace
```

### Step 4 — Generate Image Descriptions

Use the Pixtral API to generate text descriptions for images:

```bash
# Single image
python image_to_text.py chart.png

# Entire folder
python image_to_text.py --folder ./images/report --output descriptions.json

# Custom prompt
python image_to_text.py --folder ./images/report --output results.json \
  --prompt "Extract all text and numbers visible in this image"
```

### Step 5 — Inject Descriptions into Markdown

Replace image references with their generated text descriptions:

```bash
# In-place replacement
python inject_descriptions.py document.md --descriptions descriptions.json

# Save to new file
python inject_descriptions.py document.md --descriptions descriptions.json --output clean_document.md

# Process an entire folder
python inject_descriptions.py --folder ./docs --descriptions descriptions.json --output-folder ./clean_docs
```

---

## ⚙️ Pipeline Options

```bash
# Custom output path
python pipeline.py report.pdf --output clean_report.md

# Process a folder of PDFs
python pipeline.py --input-folder ./pdfs --output-folder ./markdown

# Adjust dedup sensitivity and description format
python pipeline.py report.pdf --threshold 3 --format paragraph --images-dir ./my_images

# Keep duplicates for manual review
python pipeline.py report.pdf --keep-duplicates

# Quiet mode
python pipeline.py report.pdf --quiet
```

---

## 📜 License

This project is licensed under a custom open-source license. See [LICENSE](./LICENSE) for details.

**TL;DR:**
- ✅ Free for non-commercial use with attribution
- 📩 Commercial use requires written permission
- 🔄 Modifications must be contributed back