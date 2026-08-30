# Scratchpad for polite scraper rate-limiting, cache lookup, and Pydantic validation
REQUEST_TIMEOUT_SEC = 8
POLITE_DELAY_MS = 500
RATING_LOOKUP = {'One': 1, 'Two': 2, 'Three': 3, 'Four': 4, 'Five': 5}
def parse_gbp_price(price_text: str) -> float:
    return float(str(price_text or '').replace('£', '').strip())
