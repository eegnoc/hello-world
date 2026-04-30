"""
GoodWe 8kW Battery Stack Discount Scraper

Aggregates listings from eBay, Google Shopping, and Facebook Marketplace,
then filters for GoodWe 8kW battery stacks discounted by more than 40 % off
the reference retail price.

Live sources are used when their credentials are present in the environment;
otherwise the app falls back to deterministic mock data so the dashboard
always runs without any API keys.

Environment variables (all optional – omit any to skip that source):
  EBAY_CLIENT_ID / EBAY_CLIENT_SECRET  → eBay Browse API
  SERPAPI_KEY                          → Google Shopping via SerpApi
  FB_COOKIE / FB_DTSG                  → Facebook Marketplace (unofficial)
"""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from scrapers import EbayScraper, FacebookMarketplaceScraper, GoogleShoppingScraper
from scrapers.base import RawListing

logger = logging.getLogger(__name__)

# Reference retail price used when a listing doesn't carry an original price.
GOODWE_8KW_RRP_USD = 3800.0

MODELS = [
    "GoodWe Lynx Home U 8kWh",
    "GoodWe LX U30-10 (8kW Stack)",
    "GoodWe GBLI10K (8kW)",
    "GoodWe ES-8K-ET Battery Stack",
    "GoodWe Lynx Home F 8kWh",
]


# ── Normalised listing ────────────────────────────────────────────────────────

@dataclass
class Listing:
    id: str
    source: str
    model: str
    condition: str
    original_price: float
    sale_price: float
    discount_pct: float
    in_stock: bool
    quantity_available: int
    shipping_days: int
    listing_url: str
    image_url: str
    posted_at: datetime
    expires_at: Optional[datetime]
    notes: str = ""
    warranty_years: int = 5

    @property
    def savings(self) -> float:
        return round(self.original_price - self.sale_price, 2)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "model": self.model,
            "condition": self.condition,
            "original_price": self.original_price,
            "sale_price": self.sale_price,
            "discount_pct": round(self.discount_pct, 1),
            "savings": self.savings,
            "in_stock": self.in_stock,
            "quantity_available": self.quantity_available,
            "shipping_days": self.shipping_days,
            "listing_url": self.listing_url,
            "image_url": self.image_url,
            "posted_at": self.posted_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "notes": self.notes,
            "warranty_years": self.warranty_years,
        }


# ── RawListing → Listing ──────────────────────────────────────────────────────

def _normalise(raw: RawListing, index: int) -> Optional[Listing]:
    """Convert a RawListing into a Listing, filling gaps with sensible defaults."""
    sale = raw.sale_price
    if sale <= 0:
        return None

    orig = raw.original_price or GOODWE_8KW_RRP_USD
    disc = (orig - sale) / orig * 100

    now = datetime.utcnow()
    return Listing(
        id=f"{raw.source[:3].upper()}-{index:04d}",
        source=raw.source,
        model=raw.title or "GoodWe 8kW Battery Stack",
        condition=raw.condition or "New",
        original_price=round(orig, 2),
        sale_price=round(sale, 2),
        discount_pct=disc,
        in_stock=raw.in_stock,
        quantity_available=raw.quantity_available,
        shipping_days=raw.shipping_days or 7,
        listing_url=raw.listing_url,
        image_url=raw.image_url,
        posted_at=now,
        expires_at=None,
        notes="",
        warranty_years=2 if "refurb" in raw.condition.lower() else 5,
    )


# ── Live scrapers ─────────────────────────────────────────────────────────────

def _fetch_live() -> list[Listing]:
    """Query every configured live source and return normalised listings."""
    raw_all: list[RawListing] = []

    if os.getenv("EBAY_CLIENT_ID") and os.getenv("EBAY_CLIENT_SECRET"):
        logger.info("Fetching from eBay…")
        try:
            raw_all.extend(EbayScraper().fetch_all())
        except Exception as exc:
            logger.error("eBay scraper failed: %s", exc)

    if os.getenv("SERPAPI_KEY"):
        logger.info("Fetching from Google Shopping…")
        try:
            raw_all.extend(GoogleShoppingScraper().fetch_all())
        except Exception as exc:
            logger.error("Google Shopping scraper failed: %s", exc)

    if os.getenv("FB_COOKIE") and os.getenv("FB_DTSG"):
        logger.info("Fetching from Facebook Marketplace…")
        try:
            raw_all.extend(FacebookMarketplaceScraper().fetch_all())
        except Exception as exc:
            logger.error("Facebook Marketplace scraper failed: %s", exc)

    listings: list[Listing] = []
    for i, raw in enumerate(raw_all):
        listing = _normalise(raw, i)
        if listing:
            listings.append(listing)

    return listings


# ── Mock data (fallback) ──────────────────────────────────────────────────────

def _mock_listings() -> list[Listing]:
    """Deterministic mock listings — used when no API credentials are set."""
    random.seed(42)
    now = datetime.utcnow()
    listings: list[Listing] = []

    scenarios = [
        # source,                  model,     condition,          orig,  sale,  stock, qty, ship, warr, notes
        ("eBay",                   MODELS[0], "New – Clearance",  3800, 2090, True,  3,  5,  5, "End-of-line clearance"),
        ("eBay",                   MODELS[2], "Refurbished",      3750, 2100, True,  7,  3,  2, "Grade-A refurb, tested"),
        ("Google Shopping",        MODELS[1], "New – Open Box",   3800, 2199, True,  2, 10,  5, "Opened for inspection only"),
        ("Google Shopping",        MODELS[3], "New – Clearance",  4100, 2380, True,  5,  7,  5, "Superseded by 2025 model"),
        ("Facebook Marketplace",   MODELS[4], "New",              3800, 2249, True,  1,  4,  5, "Flash sale – 48 h only"),
        ("Facebook Marketplace",   MODELS[0], "Refurbished",      3800, 2050, False, 0, 14,  2, "Out of stock – notify me"),
        ("eBay",                   MODELS[2], "New – Clearance",  3750, 2180, True,  4,  6,  5, "Tax-year-end clearance"),
        ("Google Shopping",        MODELS[1], "New",              3800, 2150, True,  8,  2,  5, "Bulk-purchase surplus"),
        # Below 40 % – filtered out
        ("eBay",                   MODELS[0], "New",              3800, 2900, True,  10, 3,  5, ""),
        ("Google Shopping",        MODELS[3], "New",              4100, 2600, True,  6,  5,  5, ""),
        ("Facebook Marketplace",   MODELS[4], "New",              3800, 2700, False, 0,  8,  5, ""),
    ]

    for i, (src, mdl, cond, orig, sale, stock, qty, ship, warr, notes) in enumerate(scenarios):
        disc = (orig - sale) / orig * 100
        days_ago = random.randint(0, 14)
        posted = now - timedelta(days=days_ago, hours=random.randint(0, 23))
        expires = None if disc < 40 else posted + timedelta(days=random.randint(3, 21))
        slug = mdl.lower().replace(" ", "-").replace("(", "").replace(")", "")
        listings.append(Listing(
            id=f"MOCK-{i+1:04d}",
            source=src,
            model=mdl,
            condition=cond,
            original_price=float(orig),
            sale_price=float(sale),
            discount_pct=disc,
            in_stock=stock,
            quantity_available=qty,
            shipping_days=ship,
            listing_url=f"https://example-solar-store.com/{slug}",
            image_url=f"https://placehold.co/300x200/1a3a5c/ffffff?text={mdl.split()[0]}+8kW",
            posted_at=posted,
            expires_at=expires,
            notes=notes,
            warranty_years=warr,
        ))

    return listings


# ── Public API ────────────────────────────────────────────────────────────────

def _has_any_credentials() -> bool:
    return bool(
        (os.getenv("EBAY_CLIENT_ID") and os.getenv("EBAY_CLIENT_SECRET"))
        or os.getenv("SERPAPI_KEY")
        or (os.getenv("FB_COOKIE") and os.getenv("FB_DTSG"))
    )


def fetch_listings(min_discount: float = 40.0, include_out_of_stock: bool = True) -> dict:
    """
    Main entry point consumed by the Flask app.

    Uses live scrapers when credentials are present; falls back to mock data
    so the dashboard always works out of the box.
    """
    using_live = _has_any_credentials()

    if using_live:
        all_listings = _fetch_live()
        data_source = "live"
    else:
        all_listings = _mock_listings()
        data_source = "mock"

    total_scraped = len(all_listings)

    filtered = [
        l for l in all_listings
        if l.discount_pct > min_discount and (include_out_of_stock or l.in_stock)
    ]
    filtered.sort(key=lambda l: l.discount_pct, reverse=True)

    in_stock_count = sum(1 for l in filtered if l.in_stock)
    avg_sale = sum(l.sale_price for l in filtered) / len(filtered) if filtered else 0
    best = filtered[0] if filtered else None

    return {
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "data_source": data_source,
        "total_scraped": total_scraped,
        "min_discount_filter": min_discount,
        "matched_count": len(filtered),
        "in_stock_count": in_stock_count,
        "avg_sale_price": round(avg_sale, 2),
        "best_deal": best.to_dict() if best else None,
        "listings": [l.to_dict() for l in filtered],
    }
