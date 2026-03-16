# 📄 crawler-ingest

A pipeline that converts PDFs into clean, vector-DB-ready markdown — extracting images, deduplicating them, generating text descriptions via AI, and injecting everything back into polished documents. Includes a web crawler to discover and download content from entire websites.

---

## ✨ Features

- **Web Crawler** — discover all pages on a site, download PDFs, convert HTML to markdown
- **CSV Reports** — detailed crawl reports for filtering and reviewing discovered content
- **PDF → Markdown** conversion with image extraction
- **DOCX → Markdown** conversion using mammoth + python-docx (tables, headings, lists)
- **XLSX → Markdown** conversion using pandas (multi-sheet, natural-language sentences)
- **Image deduplication** using perceptual hashing
- **AI-powered image descriptions** via Pixtral API
- **Automated cleanup** of duplicate references in markdown
- **Full pipeline** mode for one-command processing

---

## 🚀 Quick Start

### Crawl a website

```bash
# Discover all pages and PDFs (dry run with report)
python web_crawler.py https://example.com --dry-run

# Crawl and download everything
python web_crawler.py https://example.com -o ./crawled

# Download only PDFs
python web_crawler.py https://example.com -o ./crawled --pdfs-only
```

### Process PDFs

```bash
python pipeline.py report.pdf
```

The pipeline handles extraction, deduplication, description generation, cleanup, and injection automatically.

**Output:**
```
clean_report.md          # Final markdown ready for vector DB
images/report/           # Unique images only
  descriptions.json      # All image descriptions
  duplicate_mapping.txt  # Record of what was removed
```

### Convert DOCX files

```bash
# Single file
python docx_to_md.py report.docx

# Entire folder
python docx_to_md.py --input-folder ./docs --output-folder ./markdown
```

### Convert XLSX files

```bash
# Single file (all sheets)
python xlsx_to_md.py report.xlsx

# Entire folder
python xlsx_to_md.py --input-folder ./sheets --output-folder ./markdown
```

---

## 🌐 Web Crawler

The crawler takes a starting URL, discovers all pages on the same domain via breadth-first traversal, downloads PDFs, and converts HTML pages to markdown.

### Usage

```bash
# Dry run — discover pages and generate a CSV report
python web_crawler.py https://example.com --dry-run

# Full crawl with output
python web_crawler.py https://example.com -o ./crawled

# Only grab PDFs
python web_crawler.py https://example.com -o ./crawled --pdfs-only

# Limit scope
python web_crawler.py https://example.com -o ./crawled --max-depth 3 --max-pages 100

# Custom request delay
python web_crawler.py https://example.com -o ./crawled --delay 1.5
```

### Output Structure

```
./crawled/
  pdfs/                          # Downloaded PDFs (ready for pipeline.py)
  markdown/                      # HTML pages converted to .md
  crawl_report_<domain>_<ts>.csv # Crawl report
```

### CSV Report

A CSV report is generated automatically after each crawl (including dry runs). You can use it to review discovered pages, filter by depth, find which pages contain PDFs, and identify errors.

| Column | Description |
|--------|-------------|
| `url` | The page or PDF URL |
| `type` | `page` or `pdf` |
| `status` | `crawled`, `found` (dry-run), `downloaded`, or `error` |
| `depth` | How many links deep from the start URL |
| `title` | Page title (HTML pages only) |
| `pdf_links_count` | Number of PDFs found on that page |
| `found_on` | Parent page URL where the PDF was linked |
| `saved_as` | Local file path if downloaded |
| `size_kb` | PDF file size |
| `error` | Error message if failed |

Report options:

```bash
# Custom report path
python web_crawler.py https://example.com --dry-run --report ./report.csv

# Disable report
python web_crawler.py https://example.com -o ./crawled --no-report
```

### Crawler → Pipeline Workflow

```bash
# Step 1: Crawl and download PDFs
python web_crawler.py https://example.com -o ./crawled --pdfs-only

# Step 2: Process all downloaded PDFs
python pipeline.py --input-folder ./crawled/pdfs --output-folder ./markdown
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

## 📝 Document Conversion

### DOCX → Markdown

Converts Word documents to clean markdown using a hybrid approach: **mammoth** handles headings, paragraphs, and lists while **python-docx** renders tables as proper markdown tables.

```bash
# Single file
python docx_to_md.py report.docx

# Single file with custom output path
python docx_to_md.py report.docx --output report.md

# Entire folder (preserves sub-folder structure)
python docx_to_md.py --input-folder ./docs --output-folder ./markdown

# Quiet mode
python docx_to_md.py report.docx --quiet
```

**What it handles:**
- Headings (H1–H4), paragraphs, bullet and numbered lists
- Tables → proper `| col | col |` markdown tables
- Inline formatting: bold, italic, inline code
- Folder mode with sub-folder structure preservation

### XLSX → Markdown

Converts Excel and CSV files to natural-language markdown. Each row becomes a readable sentence, making the output meaningful for vector search and LLM reasoning.

```bash
# Single file (all sheets)
python xlsx_to_md.py report.xlsx

# Single file with custom output path
python xlsx_to_md.py report.xlsx --output report.md

# Specific sheet only
python xlsx_to_md.py report.xlsx --sheet "Summary"

# Entire folder (preserves sub-folder structure)
python xlsx_to_md.py --input-folder ./sheets --output-folder ./markdown

# Quiet mode
python xlsx_to_md.py report.xlsx --quiet
```

**What it handles:**
- `.xlsx`, `.xls`, and `.csv` files
- Multi-sheet Excel files — each sheet becomes an `## H2` section
- Unnamed first columns (e.g. dates) used as sentence prefixes
- Empty rows and columns automatically dropped

**Example output:**
```markdown
## Sales

January — Revenue: 120000, Expenses: 80000, Profit: 40000.
February — Revenue: 135000, Expenses: 85000, Profit: 50000.
```

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

## 📦 Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.9+. Set `SCALEWAY_API_KEY` environment variable for image description generation.

---

## 📜 License

This project is licensed under a custom open-source license. See [LICENSE](./LICENSE) for details.

**TL;DR:**
- ✅ Free for non-commercial use with attribution
- 📩 Commercial use requires written permission
- 🔄 Modifications must be contributed back