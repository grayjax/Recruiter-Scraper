"""
filters.py — Grad year filtering with configurable handling of unknowns.
            Title whitelist filtering (skip URL extraction for non-matching titles).
"""
from pathlib import Path
from loguru import logger

TITLE_WHITELIST_FILE = "job_titles_whitelist.txt"


def load_title_whitelist() -> set[str] | None:
    """
    Load job title whitelist from job_titles_whitelist.txt.

    Each line is a job title. Content in parentheses is stripped (alum notes,
    year ranges, etc.) so "Software Engineer (Snowflake alum)" normalizes to
    "software engineer" and will match "Senior Software Engineer".

    Returns a set of lowercase normalized phrases, or None if the file doesn't exist
    (which disables title filtering entirely).

    Matching rule (applied during scraping):
        any whitelist phrase is a substring of the candidate's title (case-insensitive)
    """
    path = Path(TITLE_WHITELIST_FILE)
    if not path.exists():
        return None

    import re
    phrases = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        # Strip parenthetical suffixes: "(Snowflake alum)", "(2021–2024)", etc.
        cleaned = re.sub(r'\s*[\(\[].*?[\)\]]', '', line).strip()
        if cleaned:
            phrases.add(cleaned.lower())

    logger.info(f"Loaded {len(phrases)} unique title phrases from {TITLE_WHITELIST_FILE}")
    return phrases


# Hard excludes — title must NOT contain any of these (case-insensitive substring).
# These override whitelist matches, which prevents broad phrases like "software engineer"
# from accidentally passing "Director of Software Engineering".
TITLE_BLACKLIST = frozenset({
    "director",
    "vice president",
    "vp",           # covers "VP of Eng", "SVP", "EVP"
    "advocate",     # covers "Developer Advocate", "Developer Advocacy"
    "advocacy",
    "merchandising",
    "operations",   # blocks ops/strategy roles; does NOT affect "devops"/"mlops"/"ops"
    "professional services",
})

# Soft flags — title passes the filter but is marked for manual review in the CSV.
TITLE_REVIEW_FLAGS = frozenset({
    "head of",      # e.g. "Head of Product" — keep but worth a human eyeball
})


def title_matches_whitelist(title: str, whitelist: set[str]) -> tuple[bool, str]:
    """
    Returns (passes: bool, review_note: str).

    1. Hard blacklist check — any match rejects the title regardless of whitelist.
       Prevents broad whitelist phrases from matching senior/exec titles.
    2. Whitelist check — at least one phrase must be a substring of the title.
    3. Soft review flags — title passes but review_note is set for manual inspection.
    """
    title_lower = title.lower()

    # Hard blacklist — overrides whitelist
    for phrase in TITLE_BLACKLIST:
        if phrase in title_lower:
            return False, ""

    # Whitelist check
    if whitelist and not any(phrase in title_lower for phrase in whitelist):
        return False, ""

    # Soft review flags
    for phrase in TITLE_REVIEW_FLAGS:
        if phrase in title_lower:
            return True, f"title: '{phrase}' — review"

    return True, ""


def apply_filters(profiles: list[dict], filter_config: dict) -> list[dict]:
    """
    Filter by Bachelor's grad year range.
    Handles profiles with no detected grad year based on config.
    """
    min_year = filter_config.get("bachelors_grad_year_min")
    max_year = filter_config.get("bachelors_grad_year_max")
    no_bachelors_action = filter_config.get("no_bachelors_action", "skip")

    if not min_year and not max_year:
        return profiles

    filtered = []
    skipped = 0
    flagged = 0

    for p in profiles:
        grad_year = p.get("bachelors_grad_year")

        if grad_year is None:
            if no_bachelors_action == "include":
                filtered.append(p)
            elif no_bachelors_action == "flag":
                p["needs_review"] = True
                filtered.append(p)
                flagged += 1
            else:  # "skip"
                skipped += 1
            continue

        if min_year and grad_year < min_year:
            skipped += 1
            continue
        if max_year and grad_year > max_year:
            skipped += 1
            continue

        filtered.append(p)

    logger.info(f"  Kept: {len(filtered)} | Skipped: {skipped} | Flagged for review: {flagged}")
    return filtered
