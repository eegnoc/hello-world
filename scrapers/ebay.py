"""
eBay Browse API scraper
========================
Official API — requires a free eBay developer account.
https://developer.ebay.com/api-docs/buy/browse/overview.html

Set env vars:
  EBAY_CLIENT_ID     – App ID from developer.ebay.com
  EBAY_CLIENT_SECRET – Cert ID from developer.ebay.com

Auth: OAuth 2.0 Client Credentials (Application token, no user login needed).
Endpoint: GET /buy/browse/v1/item_summary/search
"""

from __future__ import annotations

import base64
import os
import time
import logging
from typing import Optional

from .base import BaseScraper, RawListing

logger = logging.getLogger(__name__)

_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_SANDBOX_OAUTH_URL  = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
_SANDBOX_SEARCH_URL = "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search"


class EbayScraper(BaseScraper):
    source_name = "eBay"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        sandbox: bool = False,
    ):
        super().__init__()
        self.client_id = client_id or os.getenv("EBAY_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("EBAY_CLIENT_SECRET", "")
        self.sandbox = sandbox
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

        self._oauth_url  = _SANDBOX_OAUTH_URL  if sandbox else _OAUTH_URL
        self._search_url = _SANDBOX_SEARCH_URL if sandbox else _SEARCH_URL

    # ── Auth ────────────────────────────────────────────────────────────────

    def _ensure_token(self) -> str:
        """Return a valid Application token, refreshing when expired."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        if not self.client_id or not self.client_secret:
            raise EnvironmentError(
                "Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET to use the eBay scraper."
            )

        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        resp = self._post(
            self._oauth_url,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
        )
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + int(payload.get("expires_in", 7200))
        return self._token

    # ── Search ───────────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 20) -> list[RawListing]:
        token = self._ensure_token()

        params = {
            "q": query,
            "limit": min(limit, 200),
            # Category 41966 = Home Solar Panels; 41971 = Solar & Wind Power
            # Leave open so we don't miss listings filed under Electronics
            "filter": "conditionIds:{1000|1500|2000|2500|3000}",  # New, New other, Manufacturer refurb, Seller refurb, Used
            "sort": "price",
            "fieldgroups": "MATCHING_ITEMS,EXTENDED",
        }

        resp = self._get(
            self._search_url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        data = resp.json()
        items = data.get("itemSummaries", [])
        logger.debug("eBay '%s' → %d items", query, len(items))

        results: list[RawListing] = []
        for item in items:
            try:
                results.append(self._parse_item(item))
            except Exception as exc:
                logger.debug("eBay parse error: %s  item=%s", exc, item.get("itemId"))

        return results

    def _parse_item(self, item: dict) -> RawListing:
        price_info = item.get("price", {})
        sale_price = float(price_info.get("value", 0))
        currency = price_info.get("currency", "USD")

        # marketingPrice carries the original/RRP when eBay knows it
        marketing = item.get("marketingPrice", {})
        orig_val = marketing.get("originalPrice", {}).get("value")
        original_price = float(orig_val) if orig_val else None

        # shippingOptions → first option's maxEstimatedDeliveryDate gives days
        shipping_days = None
        for opt in item.get("shippingOptions", []):
            max_days = opt.get("maxEstimatedDeliveryDate")
            if max_days:
                from datetime import datetime
                try:
                    delta = datetime.fromisoformat(max_days.replace("Z", "+00:00")) - datetime.now().astimezone()
                    shipping_days = max(1, delta.days)
                except ValueError:
                    pass
                break

        condition_map = {
            "NEW": "New",
            "NEW_OTHER": "New – Open Box",
            "MANUFACTURER_REFURBISHED": "Refurbished",
            "SELLER_REFURBISHED": "Seller Refurbished",
            "USED": "Used",
        }
        condition = condition_map.get(
            item.get("condition", "").upper().replace(" ", "_"), item.get("condition", "")
        )

        thumbnail = ""
        if item.get("thumbnailImages"):
            thumbnail = item["thumbnailImages"][0].get("imageUrl", "")
        elif item.get("image"):
            thumbnail = item["image"].get("imageUrl", "")

        return RawListing(
            source="eBay",
            external_id=item["itemId"],
            title=item.get("title", ""),
            condition=condition,
            sale_price=sale_price,
            original_price=original_price,
            currency=currency,
            listing_url=item.get("itemWebUrl", ""),
            image_url=thumbnail,
            in_stock=item.get("availabilities", [""])[0] != "OUT_OF_STOCK"
            if item.get("availabilities")
            else True,
            quantity_available=item.get("itemGroupHrefs", [1]).__len__(),
            shipping_days=shipping_days,
            location=item.get("itemLocation", {}).get("country", ""),
            raw=item,
        )
