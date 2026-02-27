#!/usr/bin/env python3
"""
Web Crawler - Crawls websites, downloads PDFs, and converts pages to Markdown.
Integrates with the existing PDF-to-Markdown pipeline.
Uses Playwright for JavaScript-rendered content.

Usage:
    # Discover all pages (dry run) - generates report automatically
    python web_crawler.py https://example.com --dry-run

    # Crawl and save everything
    python web_crawler.py https://example.com --output-folder ./crawled

    # Crawl with PDF download only (skip HTML-to-MD)
    python web_crawler.py https://example.com --output-folder ./crawled --pdfs-only

    # Limit crawl depth
    python web_crawler.py https://example.com --output-folder ./crawled --max-depth 3

    # Limit number of pages
    python web_crawler.py https://example.com --output-folder ./crawled --max-pages 50

    # Custom delay between requests (seconds)
    python web_crawler.py https://example.com --output-folder ./crawled --delay 1.5

    # Save report to a specific path
    python web_crawler.py https://example.com --dry-run --report ./report.csv

    # Disable report generation
    python web_crawler.py https://example.com -o ./crawled --no-report

Requirements:
    pip install playwright requests beautifulsoup4 markdownify
    playwright install chromium
"""

import argparse
import csv
import os
import re
import sys
import time
import hashlib
from collections import deque
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse, unquote

import subprocess

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md


def ensure_playwright():
    """Check if Playwright is installed, install it if not."""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        print("[INFO] Playwright not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        from playwright.sync_api import sync_playwright
        return sync_playwright


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def normalize_url(url):
    """Normalize a URL for deduplication."""
    parsed = urlparse(url)
    normalized = parsed._replace(fragment="")
    path = normalized.path.rstrip("/") if normalized.path != "/" else "/"
    normalized = normalized._replace(path=path)
    return urlunparse(normalized)


def is_same_domain(url, base_domain):
    """Check if URL belongs to the same domain."""
    parsed = urlparse(url)
    return parsed.netloc == base_domain or parsed.netloc == ""


def is_valid_url(url):
    """Filter out non-HTTP URLs and unwanted patterns."""
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return False
    skip_patterns = [
        r"mailto:", r"tel:", r"javascript:", r"#$",
        r"\.(jpg|jpeg|png|gif|svg|ico|css|js|woff|woff2|ttf|eot|mp4|mp3|zip|tar|gz)$",
    ]
    for pattern in skip_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return False
    return True


def url_to_filename(url, extension=".md"):
    """Convert a URL to a safe filename."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        path = "index"
    safe_name = path.replace("/", "_")
    safe_name = re.sub(r'[^\w\-.]', '_', safe_name)
    safe_name = safe_name.strip("_.")
    if not safe_name:
        safe_name = hashlib.md5(url.encode()).hexdigest()[:12]
    if not safe_name.endswith(extension):
        safe_name = re.sub(r'\.[^.]+$', '', safe_name)
        safe_name += extension
    return safe_name


def extract_links(soup, base_url):
    """Extract all links from a BeautifulSoup object."""
    links = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href:
            continue
        absolute = urljoin(base_url, href)
        links.add(absolute)
    return links


def extract_pdf_links(soup, base_url):
    """Extract all PDF links from a page."""
    pdf_links = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if href.lower().endswith(".pdf"):
            absolute = urljoin(base_url, href)
            pdf_links.add(absolute)
    for tag in soup.find_all(["iframe", "embed", "object"], src=True):
        src = tag.get("src", "") or tag.get("data", "")
        if src and src.lower().endswith(".pdf"):
            pdf_links.add(urljoin(base_url, src))
    return pdf_links


def html_to_markdown(html, url):
    """Convert HTML content to clean Markdown."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "noscript", "nav", "footer", "header", "iframe"]):
        tag.decompose()

    # Get page title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else urlparse(url).path

    # Use body content
    body = soup.find("body")
    if body is None:
        body = soup

    # Convert to markdown
    markdown_text = md(str(body), heading_style="atx", bullets="-", strip=["img"])
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text).strip()

    return f"# {title}\n\n> Source: {url}\n\n{markdown_text}"


def download_pdf(url, output_folder, session, delay=1.0):
    """Download a PDF file."""
    try:
        time.sleep(delay)
        response = session.get(url, timeout=30, stream=True)
        response.raise_for_status()

        filename = unquote(os.path.basename(urlparse(url).path))
        if not filename.endswith(".pdf"):
            filename += ".pdf"
        filename = re.sub(r'[^\w\-.]', '_', filename)

        filepath = os.path.join(output_folder, filename)

        counter = 1
        base, ext = os.path.splitext(filepath)
        while os.path.exists(filepath):
            filepath = f"{base}_{counter}{ext}"
            counter += 1

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        size_kb = os.path.getsize(filepath) / 1024
        return filepath, size_kb
    except Exception as e:
        return None, str(e)


def generate_report(crawl_log, report_path, start_url):
    """Generate a CSV report from crawl results."""
    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)

    fieldnames = [
        "url", "type", "status", "depth", "title",
        "pdf_links_count", "found_on", "saved_as", "size_kb", "error",
    ]

    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in crawl_log:
            writer.writerow(row)

    print(f"  Report saved: {report_path}")
    print(f"  Total entries: {len(crawl_log)}")


def crawl(
    start_url,
    output_folder=None,
    max_depth=None,
    max_pages=None,
    delay=1.0,
    dry_run=False,
    pdfs_only=False,
    verbose=True,
    report_path=None,
):
    """
    Crawl a website starting from start_url.
    Uses Playwright to render JavaScript-heavy pages.

    Returns:
        dict with keys: pages_found, pages_crawled, pdfs_found, pdfs_downloaded, md_files, errors
    """
    parsed_start = urlparse(start_url)
    base_domain = parsed_start.netloc
    base_scheme = parsed_start.scheme or "https"

    if not base_domain:
        print(f"[ERROR] Invalid URL: {start_url}")
        return None

    # Setup output folders
    pdf_folder = None
    md_folder = None
    if output_folder and not dry_run:
        pdf_folder = os.path.join(output_folder, "pdfs")
        md_folder = os.path.join(output_folder, "markdown")
        os.makedirs(pdf_folder, exist_ok=True)
        os.makedirs(md_folder, exist_ok=True)

    # requests session only used for PDF downloads
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    # BFS crawl
    visited = set()
    queue = deque()
    queue.append((normalize_url(start_url), 0))

    all_pages = set()
    all_pdfs = set()
    downloaded_pdfs = []
    saved_md_files = []
    errors = []
    crawl_log = []

    pages_crawled = 0

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Web Crawler (Playwright)")
        print(f"  Target: {start_url}")
        print(f"  Domain: {base_domain}")
        print(f"  Max depth: {max_depth or 'unlimited'}")
        print(f"  Max pages: {max_pages or 'unlimited'}")
        print(f"  Delay: {delay}s")
        print(f"  Mode: {'dry run' if dry_run else 'pdfs only' if pdfs_only else 'full crawl'}")
        print(f"{'='*60}\n")

    sync_playwright = ensure_playwright()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(ignore_https_errors=True).new_page()

        while queue:
            if max_pages and pages_crawled >= max_pages:
                if verbose:
                    print(f"\n[INFO] Reached max pages limit ({max_pages})")
                break

            url, depth = queue.popleft()

            if url in visited:
                continue
            if max_depth is not None and depth > max_depth:
                continue

            visited.add(url)

            try:
                time.sleep(delay)

                response = page.goto(url, timeout=60000, wait_until="domcontentloaded")

                # Wait for JS-rendered content to load
                page.wait_for_timeout(3000)

                if response is None:
                    errors.append((url, "No response"))
                    if verbose:
                        print(f"  [ERR]  {url}: No response")
                    continue

                content_type = response.headers.get("content-type", "").lower()
                status = response.status

                # Skip non-HTML responses (but catch PDFs)
                if "application/pdf" in content_type:
                    all_pdfs.add(url)
                    saved_path = None
                    size_kb = 0
                    error_msg = ""
                    if verbose:
                        print(f"  [PDF]  {url}")
                    if not dry_run and pdf_folder:
                        path, info = download_pdf(url, pdf_folder, session, delay=0)
                        if path:
                            downloaded_pdfs.append(path)
                            saved_path = path
                            size_kb = info
                            if verbose:
                                print(f"         -> saved ({info:.1f} KB)")
                        else:
                            errors.append((url, info))
                            error_msg = info
                    crawl_log.append({
                        "url": url, "type": "pdf",
                        "status": "downloaded" if saved_path else ("found" if dry_run else "error"),
                        "depth": depth, "title": "", "pdf_links_count": 0,
                        "found_on": "direct", "saved_as": saved_path or "",
                        "size_kb": f"{size_kb:.1f}" if isinstance(size_kb, float) else "",
                        "error": error_msg,
                    })
                    continue

                if "text/html" not in content_type:
                    continue

                if status >= 400:
                    errors.append((url, f"HTTP {status}"))
                    crawl_log.append({
                        "url": url, "type": "page", "status": "error", "depth": depth,
                        "title": "", "pdf_links_count": 0, "found_on": "",
                        "saved_as": "", "size_kb": "", "error": f"HTTP {status}",
                    })
                    if verbose:
                        print(f"  [ERR]  {url}: HTTP {status}")
                    continue

                # Get the fully rendered HTML from the browser
                html_content = page.content()

                pages_crawled += 1
                all_pages.add(url)

                if verbose:
                    print(f"  [{pages_crawled:>4}]  depth={depth}  {url}")

                soup = BeautifulSoup(html_content, "html.parser")

                title_tag = soup.find("title")
                page_title = title_tag.get_text(strip=True) if title_tag else ""

                # Extract PDF links
                pdf_links = extract_pdf_links(soup, url)
                for pdf_url in pdf_links:
                    normalized_pdf = normalize_url(pdf_url)
                    if normalized_pdf not in all_pdfs:
                        all_pdfs.add(normalized_pdf)
                        saved_path = None
                        size_kb = 0
                        error_msg = ""
                        if verbose:
                            print(f"  [PDF]  {normalized_pdf}")
                        if not dry_run and pdf_folder:
                            path, info = download_pdf(normalized_pdf, pdf_folder, session, delay)
                            if path:
                                downloaded_pdfs.append(path)
                                saved_path = path
                                size_kb = info
                                if verbose:
                                    print(f"         -> saved ({info:.1f} KB)")
                            else:
                                errors.append((normalized_pdf, info))
                                error_msg = info
                        crawl_log.append({
                            "url": normalized_pdf, "type": "pdf",
                            "status": "downloaded" if saved_path else ("found" if dry_run else "error"),
                            "depth": depth, "title": "", "pdf_links_count": 0,
                            "found_on": url, "saved_as": saved_path or "",
                            "size_kb": f"{size_kb:.1f}" if isinstance(size_kb, float) else "",
                            "error": error_msg,
                        })

                # Convert page to markdown
                md_saved_path = ""
                if not dry_run and not pdfs_only and md_folder:
                    markdown_content = html_to_markdown(html_content, url)
                    if markdown_content.strip():
                        md_filename = url_to_filename(url, ".md")
                        md_path = os.path.join(md_folder, md_filename)
                        with open(md_path, "w", encoding="utf-8") as f:
                            f.write(markdown_content)
                        saved_md_files.append(md_path)
                        md_saved_path = md_path

                crawl_log.append({
                    "url": url, "type": "page", "status": "crawled", "depth": depth,
                    "title": page_title, "pdf_links_count": len(pdf_links),
                    "found_on": "", "saved_as": md_saved_path, "size_kb": "", "error": "",
                })

                # Discover new links
                links = extract_links(soup, url)
                for link in links:
                    normalized = normalize_url(link)
                    if (
                        normalized not in visited
                        and is_same_domain(normalized, base_domain)
                        and is_valid_url(normalized)
                    ):
                        queue.append((normalized, depth + 1))

            except Exception as e:
                errors.append((url, str(e)))
                crawl_log.append({
                    "url": url, "type": "page", "status": "error", "depth": depth,
                    "title": "", "pdf_links_count": 0, "found_on": "",
                    "saved_as": "", "size_kb": "", "error": str(e),
                })
                if verbose:
                    print(f"  [ERR]  {url}: {e}")

        browser.close()

    # Summary
    results = {
        "pages_found": len(all_pages),
        "pages_crawled": pages_crawled,
        "pdfs_found": len(all_pdfs),
        "pdfs_downloaded": len(downloaded_pdfs),
        "pdf_files": downloaded_pdfs,
        "md_files": saved_md_files,
        "errors": errors,
        "crawl_log": crawl_log,
    }

    if report_path:
        generate_report(crawl_log, report_path, start_url)
    elif output_folder:
        domain_name = base_domain.replace(".", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        auto_report = os.path.join(output_folder, f"crawl_report_{domain_name}_{timestamp}.csv")
        generate_report(crawl_log, auto_report, start_url)
    elif dry_run and crawl_log:
        domain_name = base_domain.replace(".", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        auto_report = f"crawl_report_{domain_name}_{timestamp}.csv"
        generate_report(crawl_log, auto_report, start_url)

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Summary")
        print(f"{'='*60}")
        print(f"  Pages found:     {results['pages_found']}")
        print(f"  Pages crawled:   {results['pages_crawled']}")
        print(f"  PDFs found:      {results['pdfs_found']}")
        if not dry_run:
            print(f"  PDFs downloaded: {results['pdfs_downloaded']}")
            print(f"  MD files saved:  {len(saved_md_files)}")
        if errors:
            print(f"  Errors:          {len(errors)}")
        if not dry_run and output_folder:
            print(f"\n  Output: {output_folder}")
            if downloaded_pdfs:
                print(f"    PDFs:     {pdf_folder}")
            if saved_md_files:
                print(f"    Markdown: {md_folder}")
        print(f"{'='*60}\n")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Crawl a website, download PDFs, and convert pages to Markdown."
    )
    parser.add_argument("url", help="Starting URL to crawl")
    parser.add_argument("--output-folder", "-o", default="./crawled", help="Output folder (default: ./crawled)")
    parser.add_argument("--max-depth", type=int, default=None, help="Maximum crawl depth (default: unlimited)")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum number of pages to crawl (default: unlimited)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds (default: 1.0)")
    parser.add_argument("--dry-run", action="store_true", help="Only discover pages and PDFs, don't download anything")
    parser.add_argument("--pdfs-only", action="store_true", help="Only download PDFs, skip HTML-to-Markdown conversion")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--report", default=None, help="Path to save CSV report (default: auto-generated in output folder)")
    parser.add_argument("--no-report", action="store_true", help="Disable CSV report generation")

    args = parser.parse_args()

    url = args.url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    report_path = None
    if not args.no_report:
        report_path = args.report

    results = crawl(
        start_url=url,
        output_folder=args.output_folder,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        delay=args.delay,
        dry_run=args.dry_run,
        pdfs_only=args.pdfs_only,
        verbose=not args.quiet,
        report_path=report_path,
    )

    if results and results["pages_crawled"] == 0:
        print(f"\n✗ Crawl failed: no pages could be crawled")
        sys.exit(1)
    elif results and results["errors"]:
        print(f"\n⚠ Crawl completed with {len(results['errors'])} error(s)")


if __name__ == "__main__":
    main()