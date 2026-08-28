# The polite scraper — A9

A small, polite scraping pipeline that downloads the first three catalogue
pages of [Books to Scrape](https://books.toscrape.com), visits all 60 book
pages, and turns the HTML into clean, schema-checked JSON — without
hammering the site, and without crashing on a broken page.

Pipeline shape: **fetch → extract → normalize → validate → store → report.**

## Target classification (Stage 0)

- **Site:** `https://books.toscrape.com`, part of the
  [toscrape.com](https://toscrape.com) sandbox family.
- **Why it's fair game:** the sandbox's own homepage describes the Books
  site as a fictional bookstore that exists specifically to be scraped,
  built as a safe practice ground for people learning scraping and for
  developers testing scraping tools. This is the only site this project
  touches.
- **Scope:** the first 3 catalogue pages only (`page-1.html` through
  `page-3.html`), which link to 60 individual book pages. No pagination
  beyond page 3, no other sections of the site.
- **Data collected:** for each book — title, price, availability text,
  star rating, description (when present), and a link back to its source
  catalogue page. No personal data, no account data, no login is involved.
- **`robots.txt` result:** `GET https://books.toscrape.com/robots.txt`
  returns **404 — no robots file found**. Per the assignment brief, a
  missing file is not itself permission; it's just a missing file. The
  actual permission is the sandbox's own front page, which explicitly
  invites scraping.

> I will not reuse this code on another site without checking its rules
> and terms first.

## Lane

Python 3.10+. `requests` for HTTP, `BeautifulSoup` for parsing, `pydantic`
for schema validation.

## Setup & run

```bash
cd scraper
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt

python src/main.py
```

That one command fetches the catalogue, visits all 60 book pages, and
writes:

- `output/books.json` — 60 validated records
- `output/errors.json` — any records that failed schema validation, with a reason
- `output/run-report.json` — counts, cache hits, duration, failures

Run it a second time and `books.json` still has exactly 60 records — the
run reads from `cache/` instead of re-hitting the site, and writing the
output file fresh each run (rather than appending) is what keeps it
idempotent.

**Prove Stage 5's failure handling** (adds one made-up book URL on purpose):

```bash
python src/main.py --inject-fake-url
```

`run-report.json` will show `"failed_pages": 1` while `books.json` still
holds the 60 good records.

**Run the parser tests** (no network calls — pure fixtures):

```bash
pip install pytest
python -m pytest tests/ -v
```

## Politeness rules

- **User-agent:** every real request identifies itself as
  `FlyRankInternshipA9/1.0 (+https://github.com/YOUR-USERNAME/scraper)` —
  update the URL to your own repo before you publish.
- **Timeout:** every request gives up after 8 seconds rather than hanging.
- **Delay:** at least 500ms between real requests to the site. Cached
  pages add no delay — they never leave the machine.
- **Cache:** every page is saved to `cache/` (git-ignored) on first fetch
  and read from there on every later run, so the site is only asked once
  per page across an entire development session.
- **Status checks:** only `200` is treated as "here is your page." `404`
  and `403` are logged and skipped without retrying — asking again won't
  help. `5xx` and timeouts get one retry with a short backoff.

## Record schema

Raw record (Stage 3, one per book page):

```json
{
  "title": "A Light in the Attic",
  "product_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
  "price_text": "£51.77",
  "availability_text": "In stock (22 available)",
  "rating_text": "Three",
  "description": null,
  "source_page": "https://books.toscrape.com/catalogue/page-1.html",
  "fetched_at": "2026-08-28T10:00:00+00:00"
}
```

Validated record (Stage 4, what actually lands in `books.json`) adds
`price_gbp` as a real number, and enforces that `product_url` and
`source_page` are well-formed absolute URLs, `title` is non-blank, and
`price_gbp` is positive. Anything that fails these checks goes to
`errors.json` with the reason instead of into `books.json`.

## Sample `run-report.json`

*(paste one real run's output here before submitting — this is a
placeholder shape, not a live result, since this repo hasn't been run
against the live site yet)*

```json
{
  "catalogue_pages_fetched": 3,
  "requests_made": 0,
  "cache_hits": 63,
  "book_urls_discovered": 60,
  "valid_records": 60,
  "invalid_records": 0,
  "failed_pages": 0
}
```

## Why this needed no browser

Books to Scrape renders its prices, availability, and descriptions
directly into the HTML the server sends — there's no client-side
JavaScript building the content afterward. A plain HTTP request already
gets everything this project needs, so reaching for a browser (Playwright,
Selenium) here would only add startup cost and memory for no extra data.
(Contrast with `quotes.toscrape.com/js`, where the quotes are injected by
JavaScript after load — that's the stretch-goal comparison.)

## Known limitation

Retries are a single fixed-delay retry on 5xx/timeout, not real
exponential backoff with jitter, and there's no `Retry-After` handling.
That's intentional — next week's assignment (A16) builds the production
version of retry logic on top of this foundation.

## Ethics note

Use an official API instead of scraping whenever one exists. Never bypass
a login wall, a paywall, or an access block — those are the site telling
you no. Collect only the fields the task actually needs, not everything
a page happens to expose. This project only ever touches a sandbox that
was built and published specifically to be scraped.
