"""
search.py — Paginate through Recruiter Lite search results.

NEW APPROACH (user feedback):
Instead of clicking each candidate individually from the search page,
we click the FIRST candidate, then use the "Next candidate" arrow button
in the profile panel to navigate through all candidates on the page.

This avoids modal conflicts and is much more efficient!
"""
from playwright.async_api import Page
from utils import random_sleep
from loguru import logger
import re
import json
import os
from pathlib import Path
from profile_navigation import process_page_via_navigation

INCREMENTAL_SAVE_FILE = "output/_incremental_profiles.jsonl"


def _save_profiles_incrementally(profiles: list[dict]):
    """
    Append profiles to a JSONL file after each page.
    This ensures data is saved even if the script is interrupted.
    """
    if not profiles:
        return
    Path(INCREMENTAL_SAVE_FILE).parent.mkdir(exist_ok=True)
    with open(INCREMENTAL_SAVE_FILE, "a", encoding="utf-8") as f:
        for profile in profiles:
            f.write(json.dumps(profile, ensure_ascii=False) + "\n")
    logger.debug(f"    Saved {len(profiles)} profiles to incremental file")


def load_incremental_profiles() -> list[dict]:
    """Load all profiles saved so far from the incremental file."""
    path = Path(INCREMENTAL_SAVE_FILE)
    if not path.exists():
        return []
    profiles = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            profiles.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return profiles


def clear_incremental_file():
    """Delete the incremental file at the start of a new run."""
    path = Path(INCREMENTAL_SAVE_FILE)
    if path.exists():
        path.unlink()


async def run_search(page: Page, search_config: dict, title_whitelist: set | None = None) -> tuple[list[dict], int]:
    """
    Navigate to saved search URL and process candidates using panel navigation.

    For each search results page:
    1. Count how many candidates are on the page
    2. Click the first candidate to open the profile panel
    3. Extract data from the panel
    4. Click "Next" in the panel to navigate to the next candidate
    5. Repeat until all candidates on the page are processed
    6. Move to the next search results page

    Returns:
        (list of profile dicts, last_page_number)
    """
    url = search_config.get("saved_search_url")
    if not url:
        raise ValueError("Provide saved_search_url in config.yaml")

    # Get start and max pages
    start_page = search_config.get("start_page", 1)
    max_pages = search_config.get("max_pages", 10)

    # Always set the start parameter in the URL to ensure we go to the right page.
    # This also strips any stale start= value the user may have pasted from a previous run.
    # LinkedIn uses start=0 for page 1, start=25 for page 2, etc.
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    start_index = (start_page - 1) * 25
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    query_params['start'] = [str(start_index)]
    new_query = urlencode(query_params, doseq=True)
    url = urlunparse((parsed.scheme, parsed.netloc, parsed.path,
                     parsed.params, new_query, parsed.fragment))

    if start_page > 1:
        logger.info(f"Navigating to starting page {start_page} (start={start_index})...")
    else:
        logger.info(f"Navigating to page 1 (forcing start=0 to reset any old URL parameter)...")

    # Use 'domcontentloaded' instead of 'networkidle' because LinkedIn
    # makes constant background requests that prevent networkidle
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await random_sleep(5, 7)  # Give extra time for dynamic content to load

    all_profiles = []
    last_page = start_page

    # Clear the incremental file at the start of a fresh run
    clear_incremental_file()

    for page_num in range(start_page, max_pages + 1):
        logger.info(f"  Page {page_num}...")
        last_page = page_num

        # Wait for result cards to load
        try:
            await page.wait_for_selector(
                "li.search-results__result-item, "
                "[data-test-search-result], "
                "li[class*='result'], "
                "div[class*='entity-result'], "
                "div[class*='search-result']",
                timeout=15000
            )
        except Exception:
            logger.warning("  Could not find search results on this page")
            break

        # ── PROCESS ALL CANDIDATES VIA PANEL NAVIGATION ──
        logger.info(f"    Processing candidates via panel navigation...")
        profiles = await process_page_via_navigation(page, title_whitelist)
        all_profiles.extend(profiles)
        logger.info(f"    ✓ Extracted {len(profiles)} profiles from page {page_num} (total: {len(all_profiles)})")

        # Check for and click "Next" to go to next search results page
        if not await _go_next(page):
            logger.info("  No more search result pages.")
            break

        await random_sleep(2, 4)

    return all_profiles, last_page


async def _scroll_to_load_all_candidates(page: Page):
    """
    Scroll to trigger LinkedIn's lazy-loading until all candidates on the page are visible.

    Root cause of "6 instead of 25" bug: the page was still rendering when we started
    counting. Only 16ms elapsed between "start scrolling" and "count = 6" - the page
    wasn't done loading yet. The "smart" early-stop then bailed immediately.

    Fix: wait for count to STABILIZE first, then scroll, then wait for stable again.
    """
    logger.debug("    Waiting for candidates to render...")

    # Root cause of missing candidates: each card is ~400-500px tall, so 25 candidates
    # = ~10,000-12,000px. Previous approach (15 × 300px = 4500px) only scrolled halfway.
    # Fix: scroll to the actual page bottom repeatedly until height stops growing.

    # Step 1: Wait for initial render
    await random_sleep(4, 6)

    count_before = await page.evaluate('document.querySelectorAll(\'a[href*="/talent/profile/"]\').length')
    logger.debug(f"    Candidates before scrolling: {count_before}")

    # Step 2: Scroll to bottom repeatedly until page height stops growing
    # (LinkedIn lazy-loads as you scroll, so new content increases the page height)
    prev_height = 0
    for attempt in range(20):  # Max 20 scroll-to-bottom attempts
        current_height = await page.evaluate("document.body.scrollHeight")
        if current_height == prev_height:
            logger.debug(f"    Page height stable at {current_height}px after {attempt} scrolls")
            break
        prev_height = current_height
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await random_sleep(1.5, 2.0)  # Wait for lazy-load to trigger

    # Step 3: Final wait for any remaining content to render
    await random_sleep(2, 3)

    count_after = await page.evaluate('document.querySelectorAll(\'a[href*="/talent/profile/"]\').length')
    logger.debug(f"    Candidates after scrolling: {count_after}")

    # Step 4: Scroll back to top so we can click the first profile
    await page.evaluate("window.scrollTo(0, 0)")
    await random_sleep(1, 2)


async def _count_candidates(page: Page) -> int:
    """
    Count how many candidates are visible on the current search results page.
    """
    return await page.evaluate("""
        () => {
            const nameLinks = document.querySelectorAll('a[href*="/talent/profile/"]');
            return nameLinks.length;
        }
    """)


async def _go_next(page: Page) -> bool:
    """
    Click the "Next page" search results pagination button.

    Confirmed from HTML inspection (screenshot with no profile panel open):
    - The mini-pagination at the top uses: a[data-test-mini-pagination-next]
      class="mini-pagination__quick-link", rel="next", title="Go to next page N"
    - The profile panel uses: a[data-test-pagination-next] (different attribute!)
    - So data-test-mini-pagination-next is the safe, specific selector for page navigation.
    """
    try:
        # Primary: the mini-pagination "Go to next page" link at the top of results
        # This is 100% specific - won't match the profile panel (data-test-pagination-next)
        next_btn = await page.query_selector(
            'a[data-test-mini-pagination-next], '
            'a.mini-pagination__quick-link[rel="next"]'
        )
        if next_btn:
            is_disabled = await next_btn.get_attribute("disabled")
            aria_disabled = await next_btn.get_attribute("aria-disabled")
            if is_disabled or aria_disabled == "true":
                logger.debug("    Next button is disabled (last page)")
                return False

            logger.debug("    Clicking Next page button...")
            await next_btn.click()
            # Don't wait for networkidle - LinkedIn makes constant background requests
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            await random_sleep(3, 4)  # Give time for new page to load
            return True
        else:
            logger.debug("    No Next button found")
            return False
    except Exception as e:
        logger.debug(f"Pagination error: {e}")
    return False
