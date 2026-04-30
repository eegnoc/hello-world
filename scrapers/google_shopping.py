"""
Google Shopping scraper
========================
Uses the SerpApi Google Shopping endpoint — the only stable, ToS-compliant
way to query Google Shopping programmatically.
https://serpapi.com/google-shopping-api

Set env var:
  SERPAPI_KEY – your SerpApi key (free tier: 100 searches/month)

Alternatively, pass api_key= to the constructor.

HTTP call:
  GET https://serpapi.com/search
      ?engine=google_shopping
      &q=<query>
      &num=20
      &api_key=<key>
"""

from __future__ import annotations

import os
import logging
from typing import Optional

from .base import BaseScraper, RawListing

logger = logging.getLogger(__name__)

_SERPAPI_URL = "https://serpapi.com/search"


class GoogleShoppingScraper(BaseScraper):
    source_name = "Google Shopping"

    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.api_key = api_key or os.getenv("SERPAPI_KEY", "")

    def search(self, query: str, limit: int = 20) -> list[RawListing]:
        if not self.api_key:
            raise EnvironmentError(
                "Set SERPAPI_KEY to use the Google Shopping scraper."
            )

        params = {
            "engine": "google_shopping",
            "q": query,
            "num": min(limit, 100),
            "gl": "us",          # country
            "hl": "en",          # language
            "api_key": self.api_key,
        }

        resp = self._get(_SERPAPI_URL, params=params)
        data = resp.json()

        shopping_results = data.get("shopping_results", [])
        logger.debug("Google Shopping '%s' → %d items", query, len(shopping_results))

        results: list[RawListing] = []
        for item in shopping_results:
            try:
                results.append(self._parse_item(item))
            except Exception as exc:
                logger.debug("Google Shopping parse error: %s  item=%s", exc, item.get("position"))

        return results

    def _parse_item(self, item: dict) -> RawListing:
        # Price can come as "$2,199.00" – strip and convert
        price_str = item.get("price", "0").replace("$", "").replace(",", "").split()[0]
        sale_price = float(price_str) if price_str else 0.0

        # "was_price" / "old_price" when a sale is shown
        orig_str = item.get("old_price", item.get("was_price", ""))
        if orig_str:
            orig_str = orig_str.replace("$", "").replace(",", "").split()[0]
        original_price = float(orig_str) if orig_str else None

        # Condition field appears in some listings
        condition_raw = item.get("second_hand_condition", "")
        condition = "Refurbished" if "refurb" in condition_raw.lower() else "New"

        return RawListing(
            source="Google Shopping",
            external_id=str(item.get("product_id") or item.get("position", "")),
            title=item.get("title", ""),
            condition=condition,
            sale_price=sale_price,
            original_price=original_price,
            currency="USD",
            listing_url=item.get("link", ""),
            image_url=item.get("thumbnail", ""),
            in_stock=True,  # Google Shopping doesn't expose stock status
            location=item.get("store", ""),
            raw=item,
        )
