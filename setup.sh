#!/bin/bash
# Set up crawler-ingest from its reviewed dependency lock.
set -euo pipefail

echo "Setting up crawler-ingest..."

python3.13 -m venv venv
venv/bin/python -m pip install --no-deps -r requirements.lock
venv/bin/python -m pip check

echo ""
echo "✓ Setup complete!"
echo ""
echo "To use the project:"
echo "  1. Activate venv: source venv/bin/activate"
echo "  2. Crawl a site:  python web_crawler.py https://example.com --dry-run"
echo "  3. Process PDFs:  python pipeline.py report.pdf"
echo "  4. Deactivate:    deactivate"
