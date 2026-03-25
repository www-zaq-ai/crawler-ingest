# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## MCP Tools

This project has two MCP tools configured — use them proactively:

**Serena** (semantic code intelligence): Use Serena tools for symbol search, go-to-definition, find references, and code navigation instead of grep/glob when working with Python code. Prefer `serena` over plain text search for anything involving function signatures, class hierarchies, or cross-file references.

**context-mode**: Use `ctx_batch_execute`, `ctx_search`, `ctx_execute`, and `ctx_execute_file` instead of Bash/Read for any operation producing >20 lines of output (log analysis, large file reads, test output, API responses, git diffs). This keeps the context window clean.

## Project Overview

A document processing pipeline that converts PDFs, DOCX, XLSX, and web pages into clean, vector-database-ready markdown for RAG/LLM applications.

## Setup & Running

```bash
pip install -r requirements.txt
playwright install chromium  # Required for web crawler
```

**Environment variable required for image description step:**
```bash
export SCALEWAY_API_KEY=<key>  # Pixtral API via Scaleway
```

## Common Commands

```bash
# Full pipeline on a single PDF
python pipeline.py report.pdf

# Crawl a website (outputs to ./crawled/pdfs/ and ./crawled/markdown/)
python web_crawler.py https://example.com -o ./crawled

# Individual pipeline steps (can be run standalone)
python pdf_to_md.py input.pdf output.md --with-images --images-dir ./images
python image_dedup.py ./images/doc --delete
python image_to_text.py --folder ./images/report --output descriptions.json
python inject_descriptions.py document.md --descriptions descriptions.json

# Convert DOCX or XLSX directly (no further pipeline steps needed)
python docx_to_md.py report.docx
python xlsx_to_md.py report.xlsx
```

## Architecture

**Two main entry points:**

1. **`web_crawler.py`** — Playwright-based BFS crawler. Stays within the same domain, downloads PDFs to `pdfs/`, converts HTML pages to markdown in `markdown/`, and writes a `crawl_report.csv`.

2. **`pipeline.py`** — Orchestrates 5 sequential steps as subprocesses:
   1. `pdf_to_md.py` — PDF → markdown + extracted images (uses `pymupdf4llm`)
   2. `image_dedup.py` — Finds visual duplicates via perceptual hashing (`imagehash`), writes `duplicate_mapping.txt`
   3. `clean_md.py` — Removes duplicate image references from markdown using the mapping
   4. `image_to_text.py` — Calls Pixtral API for each image, saves `descriptions.json`
   5. `inject_descriptions.py` — Replaces `![...](img.png)` markdown tags with AI text descriptions

**Each script is independently runnable** with its own CLI. `pipeline.py` calls them via `subprocess` using `sys.executable` and absolute paths resolved relative to `pipeline.py`'s location.

**Converters (`docx_to_md.py`, `xlsx_to_md.py`)** are standalone — not wired into `pipeline.py`. DOCX uses mammoth + python-docx; XLSX uses pandas to generate natural-language sentences per row.

## Key Design Notes

- `pipeline.py` uses `subprocess` (not imports) to call each step — this is intentional for isolation and path safety
- Script paths must be resolved relative to `pipeline.py`'s location, not the caller's CWD
- The crawler respects domain boundaries and supports `--dry-run`, `--depth`, `--delay`, and `--pdf-only` flags
- Image deduplication uses Hamming distance threshold (default: 5) on perceptual hashes — not file-level comparison
- `INGESTION_IMPROVEMENT_PLAN.md` documents planned enhancements around page-type classification, improved Pixtral prompts, and page separator metadata
