"""utils.py — Shared helpers."""
import asyncio
import random


async def random_sleep(min_sec: float = 1.0, max_sec: float = 3.0):
    """Human-like random delay."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))


# ── Location normalization ────────────────────────────────
NYC_ALIASES = [
    "new york", "brooklyn", "queens", "bronx", "manhattan",
    "staten island", "jersey city", "hoboken", "newark",
    "yonkers", "white plains", "stamford", "new rochelle",
]

SF_ALIASES = [
    "san francisco", "san jose", "oakland", "berkeley",
    "palo alto", "mountain view", "sunnyvale", "santa clara",
    "redwood city", "menlo park", "cupertino", "fremont",
    "san mateo", "daly city", "south san francisco",
    "hayward", "milpitas", "campbell", "san ramon",
]


def normalize_location(raw: str) -> str:
    """Normalize location to NYC / SF / full name."""
    lower = raw.lower().strip()

    # Strip country/state suffixes for matching
    # "Brooklyn, New York, United States" → check against aliases
    for alias in NYC_ALIASES:
        if alias in lower:
            return "NYC"

    for alias in SF_ALIASES:
        if alias in lower:
            return "SF"

    # Return the first part (city) if there are commas
    parts = raw.split(",")
    return parts[0].strip() if parts else raw.strip()
