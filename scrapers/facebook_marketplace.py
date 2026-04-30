"""
Facebook Marketplace scraper
==============================
Facebook Marketplace has NO official public API.  This module uses the
internal GraphQL endpoint that the facebook.com web app calls.

⚠️  Important caveats:
  - Facebook actively rate-limits and blocks automated requests.
  - You MUST supply a valid `fb_dtsg` token and session cookies obtained
    from a logged-in browser session (copy from DevTools → Network tab).
  - Heavy use violates Facebook's Terms of Service (§3.2).
  - Treat this as a low-volume research tool; do NOT run it continuously.

Set env vars (or pass to constructor):
  FB_COOKIE   – value of the `c_user` + `xs` cookie string from a logged-in
                Facebook browser session, e.g. "c_user=123; xs=abc..."
  FB_DTSG     – fb_dtsg token (found in page source or network requests)

HTTP call:
  POST https://www.facebook.com/api/graphql/
       Content-Type: application/x-www-form-urlencoded
       Body: fb_dtsg=<token>&variables=<json>&doc_id=<marketplace_search_doc_id>
"""

from __future__ import annotations

import json
import os
import logging
from typing import Optional

from .base import BaseScraper, RawListing

logger = logging.getLogger(__name__)

_GRAPHQL_URL = "https://www.facebook.com/api/graphql/"

# Facebook's internal doc_id for MarketplaceSearchRootQuery.
# This value changes when Facebook deploys updates — inspect network traffic
# from facebook.com/marketplace/search to find the current value.
_MARKETPLACE_DOC_ID = "7111939738879383"


class FacebookMarketplaceScraper(BaseScraper):
    source_name = "Facebook Marketplace"

    def __init__(
        self,
        cookie: Optional[str] = None,
        fb_dtsg: Optional[str] = None,
    ):
        super().__init__()
        self.cookie  = cookie  or os.getenv("FB_COOKIE", "")
        self.fb_dtsg = fb_dtsg or os.getenv("FB_DTSG",   "")

        self.session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.facebook.com",
            "Referer": "https://www.facebook.com/marketplace/",
            "X-FB-Friendly-Name": "MarketplaceSearchRootQuery",
            "X-FB-LSD": self.fb_dtsg[:16] if self.fb_dtsg else "",
        })
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie

    def search(self, query: str, limit: int = 20) -> list[RawListing]:
        if not self.cookie or not self.fb_dtsg:
            raise EnvironmentError(
                "Set FB_COOKIE and FB_DTSG to use the Facebook Marketplace scraper. "
                "See module docstring for instructions."
            )

        variables = {
            "buyLocation": {"latitude": 37.7749, "longitude": -122.4194},  # default: San Francisco
            "contextualData": None,
            "count": min(limit, 24),
            "cursor": None,
            "flashSaleEventId": "",
            "hasVideo": False,
            "itemCondition": None,
            "locale": None,
            "maxPrice": None,
            "minPrice": None,
            "query": query,
            "radius": 200,      # km
            "savedSearchID": "",
            "sellerID": None,
            "sortBy": "BEST_MATCH",
            "topicPageParams": None,
            "vehicleParams": "",
            "withCategoryFields": False,
        }

        payload = {
            "fb_dtsg":     self.fb_dtsg,
            "variables":   json.dumps(variables),
            "doc_id":      _MARKETPLACE_DOC_ID,
            "server_timestamps": "true",
        }

        resp = self._post(_GRAPHQL_URL, data=payload)
        raw = resp.json()

        # Navigate the nested GraphQL response
        edges = (
            raw
            .get("data", {})
            .get("marketplace_search", {})
            .get("feed_units", {})
            .get("edges", [])
        )
        logger.debug("FB Marketplace '%s' → %d edges", query, len(edges))

        results: list[RawListing] = []
        for edge in edges:
            try:
                results.append(self._parse_edge(edge))
            except Exception as exc:
                logger.debug("FB Marketplace parse error: %s", exc)

        return results

    def _parse_edge(self, edge: dict) -> RawListing:
        node    = edge.get("node", {})
        listing = node.get("listing", {})

        listing_id = listing.get("id", "")
        title      = listing.get("marketplace_listing_title", "")

        price_info = listing.get("listing_price", {})
        amount     = price_info.get("amount", "0")
        currency   = price_info.get("currency", "USD")
        sale_price = float(amount) / 100 if int(amount or 0) > 1000 else float(amount or 0)

        # Facebook rarely surfaces an original price; check strikethrough_price
        orig_info = listing.get("strikethrough_price") or {}
        orig_amount = orig_info.get("amount")
        original_price = (
            float(orig_amount) / 100
            if orig_amount and int(orig_amount) > 1000
            else float(orig_amount) if orig_amount
            else None
        )

        condition_raw = listing.get("condition", "")
        condition_map = {
            "NEW":           "New",
            "USED_LIKE_NEW": "New – Open Box",
            "USED_GOOD":     "Used – Good",
            "USED_FAIR":     "Used – Fair",
            "REFURBISHED":   "Refurbished",
        }
        condition = condition_map.get(condition_raw.upper(), condition_raw or "Used")

        primary_photo = (
            listing.get("primary_listing_photo", {})
            .get("image", {})
            .get("uri", "")
        )
        location_info = listing.get("location", {})
        city          = location_info.get("reverse_geocode", {}).get("city", "")

        return RawListing(
            source="Facebook Marketplace",
            external_id=listing_id,
            title=title,
            condition=condition,
            sale_price=sale_price,
            original_price=original_price,
            currency=currency,
            listing_url=f"https://www.facebook.com/marketplace/item/{listing_id}/",
            image_url=primary_photo,
            in_stock=True,
            location=city,
            raw=edge,
        )
