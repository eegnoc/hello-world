"""Base scraper interface shared by all source implementations."""

from __future__ import annotations

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

SEARCH_TERMS = [
    "GoodWe 8kWh battery",
    "GoodWe Lynx Home 8kW",
    "GoodWe GBLI10K",
    "GoodWe ES-8K battery stack",
    "GoodWe LX U30 8kW",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/json, text/html, */*",
}


@dataclass
class RawListing:
    source: str
    external_id: str
    title: str
    condition: str
    sale_price: float
    original_price: Optional[float]      # None if not disclosed
    currency: str = "USD"
    listing_url: str = ""
    image_url: str = ""
    in_stock: bool = True
    quantity_available: int = 1
    shipping_days: Optional[int] = None
    location: str = ""
    raw: dict = field(default_factory=dict)  # original response payload

    @property
    def discount_pct(self) -> Optional[float]:
        if self.original_price and self.original_price > 0:
            return (self.original_price - self.sale_price) / self.original_price * 100
        return None


class BaseScraper(ABC):
    source_name: str = "Unknown"
    RETRY_DELAYS = (2, 4, 8, 16)

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, url: str, **kwargs) -> requests.Response:
        """GET with exponential-backoff retries on transient errors."""
        for attempt, delay in enumerate([0] + list(self.RETRY_DELAYS)):
            if delay:
                time.sleep(delay)
            try:
                resp = self.session.get(url, timeout=15, **kwargs)
                if resp.status_code == 429:
                    logger.warning("%s rate-limited, backing off %ss", self.source_name, delay or 2)
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                if attempt == len(self.RETRY_DELAYS):
                    raise
                logger.warning("%s request failed (%s), retrying…", self.source_name, exc)
        raise RuntimeError(f"{self.source_name}: exhausted retries for {url}")

    def _post(self, url: str, **kwargs) -> requests.Response:
        for attempt, delay in enumerate([0] + list(self.RETRY_DELAYS)):
            if delay:
                time.sleep(delay)
            try:
                resp = self.session.post(url, timeout=15, **kwargs)
                if resp.status_code == 429:
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                if attempt == len(self.RETRY_DELAYS):
                    raise
                logger.warning("%s POST failed (%s), retrying…", self.source_name, exc)
        raise RuntimeError(f"{self.source_name}: exhausted retries for {url}")

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> list[RawListing]:
        """Return raw listings for a single search query."""

    def fetch_all(self, limit_per_query: int = 20) -> list[RawListing]:
        """Run all SEARCH_TERMS and deduplicate by external_id."""
        seen: set[str] = set()
        results: list[RawListing] = []
        for term in SEARCH_TERMS:
            try:
                for listing in self.search(term, limit=limit_per_query):
                    if listing.external_id not in seen:
                        seen.add(listing.external_id)
                        results.append(listing)
            except Exception as exc:
                logger.error("%s search('%s') failed: %s", self.source_name, term, exc)
        return results
