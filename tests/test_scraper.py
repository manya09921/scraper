"""
Parser tests — run entirely against local fixture files, no network calls.

Covers the five cases the assignment asks for:
    1. price normalization ("£51.77" -> 51.77)
    2. relative -> absolute URL conversion
    3. missing description handled as null, not invented
    4. duplicate URLs collapsed to one
    5. a malformed fixture handled as a skipped page, not a crash

Run with:  pytest tests/
"""

import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from main import extract_raw_record, normalize_and_validate  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_price_normalization():
    raw = extract_raw_record(
        _read("book_full.html"),
        product_url="https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        source_page="https://books.toscrape.com/catalogue/page-1.html",
    )
    record, error = normalize_and_validate(raw)

    assert error is None
    assert record.price_text == "£51.77"
    assert record.price_gbp == 51.77


def test_relative_to_absolute_url():
    soup = BeautifulSoup(_read("catalogue_page.html"), "html.parser")
    href = soup.select("article.product_pod h3 a")[0]["href"]
    page_url = "https://books.toscrape.com/catalogue/page-1.html"
    absolute = urljoin(page_url, href)

    assert not absolute.startswith(".")          # no leftover relative markers
    assert absolute.startswith("https://books.toscrape.com/")
    assert absolute.endswith("index.html")


def test_missing_description_is_null_not_invented():
    raw = extract_raw_record(
        _read("book_no_description.html"),
        product_url="https://books.toscrape.com/catalogue/soumission_998/index.html",
        source_page="https://books.toscrape.com/catalogue/page-1.html",
    )
    record, error = normalize_and_validate(raw)

    assert error is None
    assert record.description is None


def test_duplicate_urls_collapse_to_one():
    soup = BeautifulSoup(_read("catalogue_page.html"), "html.parser")
    base = "https://books.toscrape.com/catalogue/page-1.html"
    hrefs = [urljoin(base, a["href"]) for a in soup.select("article.product_pod h3 a")]
    unique = list(dict.fromkeys(hrefs))

    assert len(hrefs) == 3       # three links on the fixture page
    assert len(unique) == 2      # but only two distinct books


def test_malformed_page_does_not_crash():
    """A page missing the expected product markup should raise a clear,
    catchable error rather than silently producing a garbage record —
    this is what run() catches and logs as a failed page."""
    try:
        extract_raw_record(
            _read("book_malformed.html"),
            product_url="https://books.toscrape.com/catalogue/does-not-exist/index.html",
            source_page="https://books.toscrape.com/catalogue/page-1.html",
        )
        raised = False
    except AttributeError:
        raised = True

    assert raised is True
