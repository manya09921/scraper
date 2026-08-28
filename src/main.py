"""
The polite scraper — FlyRank Internship, Backend Track, W5, A9.

Fetches the first 3 catalogue pages of https://books.toscrape.com,
visits all 60 book pages, turns the messy HTML into clean, checked
JSON records, survives a broken page without crashing, and ends with
an honest run report.

Run:
    python src/main.py
    python src/main.py --inject-fake-url   # Stage 5 failure-handling proof
    python src/main.py --no-delay          # skip politeness delay (cache-only reruns)

Every stage in this file matches a stage in the assignment brief:
    0. classify_target()      -> README + robots.txt check (see README.md)
    1. fetch()                -> fetch once, cache once
    2. discover_book_urls()   -> find all three catalogue pages
    3. extract_raw_record()   -> extract the raw records
    4. normalize_and_validate() -> clean it, check it, store it
    5. run()                  -> one bad page must not kill the run
    6. (README.md)            -> publish the evidence
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin
from urllib.error import URLError

import requests
from bs4 import BeautifulSoup
from pydantic import ValidationError

from schema import BookRecord, RawBookRecord

BASE_URL = "https://books.toscrape.com/"
CATALOGUE_URL = "https://books.toscrape.com/catalogue/page-1.html"
USER_AGENT = "FlyRankInternshipA9/1.0 (+https://github.com/manya09921/scraper)"
TIMEOUT_SECONDS = 8
POLITE_DELAY_SECONDS = 0.5
MAX_CATALOGUE_PAGES = 3
RETRYABLE_STATUS = set(range(500, 600))

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache"
OUTPUT_DIR = ROOT / "output"

RATING_WORDS = {"One", "Two", "Three", "Four", "Five"}


class FetchResult:
    """Outcome of one fetch attempt — used by both catalogue and book pages."""

    def __init__(self, url: str, ok: bool, html: Optional[str] = None,
                 status: Optional[int] = None, from_cache: bool = False,
                 reason: Optional[str] = None):
        self.url = url
        self.ok = ok
        self.html = html
        self.status = status
        self.from_cache = from_cache
        self.reason = reason


def _cache_path_for(url: str) -> Path:
    """Deterministic cache filename for any URL (catalogue or book page)."""
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    slug = url.rstrip("/").rsplit("/", 1)[-1] or "page"
    return CACHE_DIR / f"{slug}-{digest}.html"


def fetch(session: requests.Session, url: str, stats: dict, retry: bool = True) -> FetchResult:
    """
    Stage 1 (reused in Stage 3): fetch once, cache once.

    - Reads from cache when present (no delay, no network hit).
    - Otherwise makes a polite request: honest user-agent, timeout,
      status check, then saves the HTML to cache.
    - Retries once on a timeout or 5xx. Never retries a 404 or 403 —
      those are answers, not glitches.
    """
    cache_path = _cache_path_for(url)

    if cache_path.exists():
        stats["cache_hits"] += 1
        return FetchResult(url, ok=True, html=cache_path.read_text(encoding="utf-8"),
                            status=200, from_cache=True)

    attempts = 2 if retry else 1
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_error = f"network error: {exc}"
            stats["requests_made"] += 1
            time.sleep(POLITE_DELAY_SECONDS)
            if attempt < attempts:
                time.sleep(1.0 * attempt)  # brief backoff before the one retry
                continue
            return FetchResult(url, ok=False, reason=last_error)

        stats["requests_made"] += 1

        if resp.status_code == 200:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(resp.text, encoding="utf-8")
            print(f"FETCH  {url}  status=200  size={len(resp.text)}")
            time.sleep(POLITE_DELAY_SECONDS)
            return FetchResult(url, ok=True, html=resp.text, status=200, from_cache=False)

        if resp.status_code in RETRYABLE_STATUS and attempt < attempts:
            time.sleep(1.0 * attempt)
            continue

        # 404, 403, or a repeated 5xx: this is a failed page, not a page to parse.
        time.sleep(POLITE_DELAY_SECONDS)
        return FetchResult(url, ok=False, status=resp.status_code,
                            reason=f"HTTP {resp.status_code}")

    return FetchResult(url, ok=False, reason=last_error or "unknown fetch failure")


def discover_book_urls(session: requests.Session, stats: dict) -> list[str]:
    """Stage 2: find all three catalogue pages, follow 'next', collect unique book URLs."""
    urls: list[str] = []
    page_url = CATALOGUE_URL
    pages_seen = 0

    while page_url and pages_seen < MAX_CATALOGUE_PAGES:
        result = fetch(session, page_url, stats)
        if not result.ok:
            print(f"WARN  could not fetch catalogue page {page_url}: {result.reason}")
            break

        pages_seen += 1
        soup = BeautifulSoup(result.html, "html.parser")

        for article in soup.select("article.product_pod h3 a"):
            href = article.get("href")
            if href:
                urls.append(urljoin(page_url, href))

        next_link = soup.select_one("li.next a")
        page_url = urljoin(page_url, next_link.get("href")) if next_link else None

    unique_urls = list(dict.fromkeys(urls))  # de-dupe, keep order
    print(f"catalogue_pages={pages_seen} discovered={len(urls)} unique_urls={len(unique_urls)}")
    stats["catalogue_pages_fetched"] = pages_seen
    return unique_urls


def extract_raw_record(html: str, product_url: str, source_page: str) -> RawBookRecord:
    """Stage 3: pull the eight raw fields out of one book page. No cleanup yet."""
    soup = BeautifulSoup(html, "html.parser")
    product = soup.select_one("div.product_main")

    title = product.find("h1").get_text(strip=True)
    price_text = product.select_one("p.price_color").get_text(strip=True)
    availability_text = product.select_one("p.availability").get_text(strip=True)

    rating_classes = product.select_one("p.star-rating")["class"]
    rating_text = next((c for c in rating_classes if c in RATING_WORDS), "Unknown")

    desc_heading = soup.select_one("#product_description")
    description = None
    if desc_heading:
        desc_p = desc_heading.find_next_sibling("p")
        description = desc_p.get_text(strip=True) if desc_p else None

    return RawBookRecord(
        title=title,
        product_url=product_url,
        price_text=price_text,
        availability_text=availability_text,
        rating_text=rating_text,
        description=description,
        source_page=source_page,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


def normalize_and_validate(raw: RawBookRecord) -> tuple[Optional[BookRecord], Optional[str]]:
    """
    Stage 4: turn '£51.77' into 51.77, keep the original text, validate the
    whole shape against the schema. Returns (record, None) on success,
    or (None, reason) if the record must go to errors.json instead.
    """
    try:
        price_gbp = float(raw.price_text.replace("£", "").replace("Â", "").strip())
    except ValueError as exc:
        return None, f"could not parse price_text {raw.price_text!r}: {exc}"

    try:
        record = BookRecord(
            title=raw.title,
            product_url=raw.product_url,
            price_text=raw.price_text,
            price_gbp=price_gbp,
            availability_text=raw.availability_text,
            rating_text=raw.rating_text,
            description=raw.description,
            source_page=raw.source_page,
            fetched_at=raw.fetched_at,
        )
        return record, None
    except ValidationError as exc:
        return None, str(exc)


def run(inject_fake_url: bool = False) -> None:
    start = time.time()
    started_at = datetime.now(timezone.utc).isoformat()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stats = {"cache_hits": 0, "requests_made": 0, "catalogue_pages_fetched": 0}
    session = requests.Session()

    book_urls = discover_book_urls(session, stats)

    if inject_fake_url:
        fake_url = urljoin(BASE_URL, "catalogue/this-book-does-not-exist_9999/index.html")
        book_urls.append(fake_url)
        print(f"INJECTED fake URL for Stage 5 proof: {fake_url}")

    valid_records: list[dict] = []
    error_records: list[dict] = []
    failed_pages: list[dict] = []
    seen_canonical: set[str] = set()

    for url in book_urls:
        result = fetch(session, url, stats)

        if not result.ok:
            print(f"SKIP  {url}  ({result.reason})")
            failed_pages.append({"url": url, "reason": result.reason})
            continue

        try:
            raw = extract_raw_record(result.html, product_url=url, source_page=CATALOGUE_URL)
        except AttributeError as exc:
            # A page that returned 200 but doesn't have the shape we expect —
            # still "one bad page," handled the same way.
            print(f"SKIP  {url}  (unexpected page shape: {exc})")
            failed_pages.append({"url": url, "reason": f"unexpected page shape: {exc}"})
            continue

        record, error_reason = normalize_and_validate(raw)

        if record is None:
            error_records.append({"raw": raw.model_dump(), "reason": error_reason})
            continue

        canonical = str(record.product_url)
        if canonical in seen_canonical:
            continue  # idempotency: same book seen twice in one run counts once
        seen_canonical.add(canonical)

        valid_records.append(json.loads(record.model_dump_json()))

    (OUTPUT_DIR / "books.json").write_text(
        json.dumps(valid_records, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / "errors.json").write_text(
        json.dumps(error_records, indent=2), encoding="utf-8"
    )

    duration = round(time.time() - start, 2)
    report = {
        "started_at": started_at,
        "duration_seconds": duration,
        "catalogue_pages_fetched": stats["catalogue_pages_fetched"],
        "requests_made": stats["requests_made"],
        "cache_hits": stats["cache_hits"],
        "book_urls_discovered": len(book_urls),
        "valid_records": len(valid_records),
        "invalid_records": len(error_records),
        "failed_pages": len(failed_pages),
        "failed_page_details": failed_pages,
    }
    (OUTPUT_DIR / "run-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print("\n--- run report ---")
    print(json.dumps(report, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="The polite scraper (A9)")
    parser.add_argument(
        "--inject-fake-url", action="store_true",
        help="Add one made-up book URL to prove Stage 5's failure handling.",
    )
    args = parser.parse_args()
    run(inject_fake_url=args.inject_fake_url)


if __name__ == "__main__":
    main()
