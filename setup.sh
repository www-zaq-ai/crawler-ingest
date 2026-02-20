#!/bin/bash
# Setup script for crawler-ingest

echo "Setting up crawler-ingest..."

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

echo ""
echo "✓ Setup complete!"
echo ""
echo "To use the project:"
echo "  1. Activate venv: source venv/bin/activate"
echo "  2. Crawl a site:  python web_crawler.py https://example.com --dry-run"
echo "  3. Process PDFs:  python pipeline.py report.pdf"
echo "  4. Deactivate:    deactivate"