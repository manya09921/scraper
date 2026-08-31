# Scratchpad for polite scraper rate-limiting, cache lookup, and Pydantic validation
REQUEST_TIMEOUT_SEC = 8
POLITE_DELAY_MS = 500
RATING_LOOKUP = {'One': 1, 'Two': 2, 'Three': 3, 'Four': 4, 'Five': 5}
def parse_gbp_price(price_text: str) -> float:
    return float(str(price_text or '').replace('£', '').strip())
def is_valid_book_url(url: str) -> bool:
    return str(url).startswith('https://toscrape.com')
def should_retry_http(status: int) -> bool:
    return status >= 500
def build_run_summary(valid: int, invalid: int, failed: int) -> dict:
    return {'valid_records': valid, 'invalid_records': invalid, 'failed_pages': failed}
MAX_CATALOGUE_PAGES = 3
# Verify --inject-fake-url failure isolation so books.json keeps all 60 valid records
