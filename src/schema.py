"""
Schema definitions for the polite scraper (Assignment A9).

Two shapes live here on purpose:

- RawBookRecord: exactly what Stage 3 pulls off the page. Nothing is
  computed, nothing is coerced beyond what BeautifulSoup already gives us.
- BookRecord: the checked, normalized shape from Stage 4. This is the
  only shape allowed into output/books.json.

Keeping both means we never lose the "receipt" (raw text, source page,
fetch time) even after normalization.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, HttpUrl, field_validator


class RawBookRecord(BaseModel):
    title: str
    product_url: str
    price_text: str
    availability_text: str
    rating_text: str
    description: Optional[str] = None
    source_page: str
    fetched_at: str


class BookRecord(BaseModel):
    """The validated, normalized record. This is what lands in books.json."""

    title: str
    product_url: HttpUrl
    price_text: str
    price_gbp: float
    availability_text: str
    rating_text: str
    description: Optional[str] = None
    source_page: HttpUrl
    fetched_at: datetime

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title is blank")
        return v.strip()

    @field_validator("price_gbp")
    @classmethod
    def price_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"price_gbp must be positive, got {v}")
        return v
