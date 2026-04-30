"""
GoodWe 8kW Battery Stack Discount Scraper

Searches multiple sources for GoodWe 8kW battery stacks and filters
listings where the discount exceeds 40% off the reference/RRP price.
"""

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


GOODWE_8KW_RRP_USD = 3800.0  # Typical retail reference price for GoodWe 8kW (Lynx Home U)

SOURCES = [
    "SolarEdgeDirect",
    "RenewableOutlet",
    "EcoVolt Shop",
    "SunPower Store",
    "BatteriesPlus Solar",
    "GreenGridSupply",
    "AltEnergyStore",
    "SolarWarehouse",
]

MODELS = [
    "GoodWe Lynx Home U 8kWh",
    "GoodWe LX U30-10 (8kW Stack)",
    "GoodWe GBLI10K (8kW)",
    "GoodWe ES-8K-ET Battery Stack",
    "GoodWe Lynx Home F 8kWh",
]

CONDITIONS = ["New", "New – Open Box", "Refurbished", "New – Clearance"]


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


def _seeded_listings() -> list[Listing]:
    """
    Generate deterministic mock listings that simulate real marketplace data.
    In production this would be replaced by actual HTTP requests to APIs/scrapers.
    """
    random.seed(42)
    now = datetime.utcnow()
    listings: list[Listing] = []

    scenarios = [
        # (source, model, condition, original, sale, in_stock, qty, ship_days, warranty, notes)
        ("SolarEdgeDirect",  MODELS[0], "New – Clearance",    3800, 2090, True,  3,  5,  5, "End-of-line clearance stock"),
        ("RenewableOutlet",  MODELS[2], "Refurbished",        3750, 2100, True,  7,  3,  2, "Grade-A refurb, tested to spec"),
        ("EcoVolt Shop",     MODELS[1], "New – Open Box",     3800, 2199, True,  2, 10,  5, "Opened for inspection only"),
        ("SunPower Store",   MODELS[3], "New – Clearance",    4100, 2380, True,  5,  7,  5, "Superseded by 2025 model"),
        ("BatteriesPlus Solar", MODELS[4], "New",             3800, 2249, True,  1,  4,  5, "Flash sale – 48 h only"),
        ("GreenGridSupply",  MODELS[0], "Refurbished",        3800, 2050, False, 0, 14,  2, "Out of stock – notify me"),
        ("AltEnergyStore",   MODELS[2], "New – Clearance",    3750, 2180, True,  4,  6,  5, "Tax-year-end clearance"),
        ("SolarWarehouse",   MODELS[1], "New",                3800, 2150, True,  8,  2,  5, "Bulk-purchase surplus"),
        # Below 40 % – should be filtered out
        ("SolarEdgeDirect",  MODELS[0], "New",                3800, 2900, True,  10, 3,  5, ""),
        ("RenewableOutlet",  MODELS[3], "New",                4100, 2600, True,  6,  5,  5, ""),
        ("EcoVolt Shop",     MODELS[4], "New",                3800, 2700, False, 0,  8,  5, ""),
    ]

    for i, (src, mdl, cond, orig, sale, stock, qty, ship, warr, notes) in enumerate(scenarios):
        disc = (orig - sale) / orig * 100
        days_ago = random.randint(0, 14)
        posted = now - timedelta(days=days_ago, hours=random.randint(0, 23))
        expires = None if disc < 40 else posted + timedelta(days=random.randint(3, 21))
        slug = mdl.lower().replace(" ", "-").replace("(", "").replace(")", "")
        listings.append(Listing(
            id=f"LST-{i+1:04d}",
            source=src,
            model=mdl,
            condition=cond,
            original_price=float(orig),
            sale_price=float(sale),
            discount_pct=disc,
            in_stock=stock,
            quantity_available=qty,
            shipping_days=ship,
            listing_url=f"https://example-solar-store.com/{slug}?ref=goodwe-dashboard",
            image_url=f"https://placehold.co/300x200/1a3a5c/ffffff?text={mdl.split()[0]}+8kW",
            posted_at=posted,
            expires_at=expires,
            notes=notes,
            warranty_years=warr,
        ))

    return listings


def fetch_listings(min_discount: float = 40.0, include_out_of_stock: bool = True) -> dict:
    """
    Main entry point. Returns filtered listings plus aggregate stats.

    Args:
        min_discount: Minimum discount percentage (exclusive lower bound).
        include_out_of_stock: When False, only return listings with stock > 0.
    """
    time.sleep(0.3)  # simulate network latency

    all_listings = _seeded_listings()
    total_scraped = len(all_listings)

    filtered = [
        l for l in all_listings
        if l.discount_pct > min_discount and (include_out_of_stock or l.in_stock)
    ]
    filtered.sort(key=lambda l: l.discount_pct, reverse=True)

    in_stock_count = sum(1 for l in filtered if l.in_stock)
    avg_sale = (
        sum(l.sale_price for l in filtered) / len(filtered) if filtered else 0
    )
    best = filtered[0] if filtered else None

    return {
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "total_scraped": total_scraped,
        "min_discount_filter": min_discount,
        "matched_count": len(filtered),
        "in_stock_count": in_stock_count,
        "avg_sale_price": round(avg_sale, 2),
        "best_deal": best.to_dict() if best else None,
        "listings": [l.to_dict() for l in filtered],
    }
