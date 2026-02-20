"""
profile_navigation.py — Navigate through profiles using the panel's Next button.

APPROACH:
1. Click the first candidate link on the search page to open the panel.
2. Extract data from the panel.
3. Click the panel's "Next candidate" button.
4. Repeat until Next is disabled (last candidate on the page).
5. Close the panel.

No candidate counting needed — the Next button itself tells us when we're done.
All data is extracted from the panel's own lockup elements (not search result cards).
"""
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from utils import random_sleep, normalize_location
from loguru import logger
import asyncio
import re


async def _is_chrome_crashed(page: Page) -> bool:
    """
    Detect if Chrome has crashed (shows "Aw, Snap!" or similar error page).
    After heavy memory usage, LinkedIn tabs can crash — this detects it.
    """
    try:
        title = await page.title()
        if any(phrase in title.lower() for phrase in ["aw, snap", "error", "page unresponsive"]):
            return True
        # Also check page content as fallback
        content = await page.evaluate("() => document.body?.innerText || ''")
        if "aw, snap" in content.lower():
            return True
        return False
    except Exception:
        # If we can't even read the page, assume it's crashed
        return True


async def process_page_via_navigation(
    page: Page,
    title_whitelist: set | None = None,
    page_num: int = 0
) -> list[dict]:
    """
    Process all candidates on the current search page by opening the first
    candidate's profile panel and repeatedly clicking Next until done.

    Args:
        page: Playwright page object
        title_whitelist: Set of approved job title phrases
        page_num: Current search page number (for crash recovery messages)

    Returns:
        List of extracted profile data dicts
    """
    profiles = []

    # ── Close any interfering modals ──────────────────────────────
    try:
        hiring_assistant = await page.query_selector('[data-test-liha-panel]')
        if hiring_assistant:
            logger.info("  Closing Hiring Assistant panel...")
            close_btn = await page.query_selector('[data-test-liha-panel] button[aria-label*="Close"]')
            if close_btn:
                await close_btn.click()
                await random_sleep(1, 2)
    except Exception as e:
        logger.debug(f"  Error checking for modals: {e}")

    # ── Click the first candidate to open the panel ───────────────
    logger.info("  Opening first candidate profile...")
    first_link = await page.query_selector('a[href*="/talent/profile/"]')
    if not first_link:
        logger.warning("  Could not find any candidate links on this page")
        return profiles

    candidate_name = (await first_link.text_content() or "").strip()
    logger.info(f"    Clicking: {candidate_name}")

    await first_link.scroll_into_view_if_needed()
    await random_sleep(0.5, 1)
    await first_link.click()
    await random_sleep(3, 4)

    # Wait for panel to open
    try:
        await page.wait_for_selector(
            'a:has-text("Public profile"), '
            '[data-test-summary-card-text], '
            'button:has-text("Save to pipeline")',
            timeout=10000
        )
        logger.debug("  Profile panel opened")
    except Exception as e:
        logger.warning(f"  Profile panel did not open: {e}")
        await page.screenshot(path="output/debug_panel_open_failed.png")
        return profiles

    # Import here to avoid circular import
    from search import _save_profiles_incrementally

    # ── Loop: extract → Next → extract → Next → ... ───────────────
    candidate_num = 0
    try:
        while True:
            candidate_num += 1

            # Check for Chrome crash before processing
            if await _is_chrome_crashed(page):
                resume_msg = f"page {page_num}, candidate {candidate_num}" if page_num else f"candidate {candidate_num}"
                logger.error(
                    f"\n"
                    f"  ╔══════════════════════════════════════════════════════╗\n"
                    f"  ║  Chrome tab crashed (memory overload)                ║\n"
                    f"  ║  Saved {len(profiles)} profiles from this page       ║\n"
                    f"  ║                                                      ║\n"
                    f"  ║  TO RESUME:                                          ║\n"
                    f"  ║  1. Refresh the Chrome tab (Cmd+R / Ctrl+R)          ║\n"
                    f"  ║  2. Wait for LinkedIn Recruiter to reload            ║\n"
                    f"  ║  3. Resume scraper from {resume_msg:30s} ║\n"
                    f"  ╚══════════════════════════════════════════════════════╝\n"
                )
                break

            logger.info(f"  [{candidate_num}] Extracting profile data...")

            profile_data = await _extract_from_open_panel(page, title_whitelist)

            if profile_data:
                profiles.append(profile_data)
                _save_profiles_incrementally([profile_data])
                logger.debug(f"    ✓ {profile_data.get('full_name', 'Unknown')} | "
                             f"{profile_data.get('current_title', '')} @ "
                             f"{profile_data.get('current_company', '')}")

                # Periodic checkpoint every 50 profiles
                if candidate_num % 50 == 0:
                    logger.info(f"  ✓ Checkpoint: {candidate_num} candidates processed, {len(profiles)} saved from this page")
            else:
                logger.warning(f"    ✗ Failed to extract data for candidate {candidate_num}")

            # Try to advance to next candidate
            if not await _click_next_candidate(page):
                logger.info(f"  Done — processed {candidate_num} candidate(s) on this page")
                break

            await random_sleep(2, 3)

    except (PlaywrightTimeoutError, asyncio.TimeoutError) as e:
        resume_msg = f"page {page_num}, candidate {candidate_num}" if page_num else f"candidate {candidate_num}"
        logger.error(
            f"\n"
            f"  ╔══════════════════════════════════════════════════════╗\n"
            f"  ║  Timeout after {len(profiles)} profiles              ║\n"
            f"  ║  Likely cause: Chrome crashed or LinkedIn froze      ║\n"
            f"  ║                                                      ║\n"
            f"  ║  TO RESUME:                                          ║\n"
            f"  ║  1. Refresh the Chrome tab                           ║\n"
            f"  ║  2. Wait for LinkedIn Recruiter to reload            ║\n"
            f"  ║  3. Resume scraper from {resume_msg:30s} ║\n"
            f"  ╚══════════════════════════════════════════════════════╝\n"
        )
    except Exception as e:
        resume_msg = f"page {page_num}, candidate {candidate_num}" if page_num else f"candidate {candidate_num}"
        logger.error(
            f"\n  Unexpected error after {len(profiles)} profiles: {e}\n"
            f"  Saved progress — resume from {resume_msg}\n"
        )

    # ── Close the panel ───────────────────────────────────────────
    logger.debug("  Closing profile panel...")
    await _close_profile_panel(page)
    await random_sleep(1, 2)

    return profiles


async def _extract_from_open_panel(page: Page, title_whitelist: set | None = None) -> dict | None:
    """
    Extract all data from the currently open profile panel.

    All selectors use confirmed data-test-* attributes from HTML inspection —
    these are stable because LinkedIn uses them for their own test suite.

    Primary source: Experience section (first position entry, DOM order = most recent)
      Standalone positions (single role at employer):
        - data-test-position-entity-title       → job title
        - data-test-position-entity-company-link → company name
        - data-test-position-entity-location     → location
      Grouped positions (multiple roles at same employer):
        - data-test-grouped-position-entity-title       → job title (most recent sub-role)
        - data-test-grouped-position-entity-company-link → company name
        - data-test-grouped-position-entity-location     → location
    Fallback: Panel header lockup
      - data-test-row-lockup-full-name         → name
      - data-test-row-lockup-headline          → title (if experience missing)
      - data-test-topcard-condensed-lockup-current-employer → company (if experience missing)
      - data-test-row-lockup-location          → location (if experience missing)
    """
    try:
        await random_sleep(1, 2)

        panel_data = await page.evaluate("""
            () => {
                const result = {
                    name: '',
                    title: '',
                    company: '',
                    location: '',
                    debug: []
                };

                // ── Name (panel header) ───────────────────────────
                // Confirmed: span[data-test-row-lockup-full-name]
                const nameEl = document.querySelector('[data-test-row-lockup-full-name]');
                if (nameEl) {
                    result.name = nameEl.textContent.trim();
                    result.debug.push(`Name: "${result.name}"`);
                }

                // Helper: get text from an element WITHOUT the hidden popover content.
                // LinkedIn injects "[data-test-hoverable-popover-content]" divs inside
                // clickable elements — these contain "Related to search terms in your query"
                // which is invisible on screen but included in .textContent.
                // Fix: clone → strip popovers → read textContent.
                function cleanText(el) {
                    if (!el) return '';
                    const clone = el.cloneNode(true);
                    for (const pop of clone.querySelectorAll('[data-test-hoverable-popover-content]')) {
                        pop.remove();
                    }
                    // Collapse all whitespace (newlines/tabs from nested divs) to single spaces
                    return clone.textContent.replace(/\s+/g, ' ').trim();
                }

                // ── Title: Handle both standalone and grouped position types ──
                // LinkedIn uses two different HTML structures for experience entries:
                //   Standalone (single role at employer):
                //     data-test-position-entity-title
                //   Grouped (multiple roles at same employer, shown as nested list):
                //     data-test-grouped-position-entity-title
                //
                // querySelector with a combined selector returns the FIRST match in
                // DOM order. LinkedIn renders experience most-recent-first, so [0]
                // gives us the current role regardless of which structure is used.
                const titleEl = document.querySelector(
                    '[data-test-grouped-position-entity-title], [data-test-position-entity-title]'
                );
                if (titleEl) {
                    result.title = cleanText(titleEl);
                    result.debug.push(`Title (experience): "${result.title}"`);
                }

                // ── Company: Same dual-selector approach ───────────────────────
                // For grouped: data-test-grouped-position-entity-company-link
                //   (appears at the top of the group block, before the role titles)
                // For standalone: data-test-position-entity-company-link
                const companyEl = document.querySelector(
                    '[data-test-grouped-position-entity-company-link], [data-test-position-entity-company-link]'
                );
                if (companyEl) {
                    result.company = cleanText(companyEl);
                    result.debug.push(`Company (experience): "${result.company}"`);
                }

                // ── Location: Scoped to FIRST job only ──────────────────────
                // Previously querySelector searched ALL experience entries, so if the
                // most recent job had no location it grabbed text from an older job
                // (e.g. a department name like "Network Infrastructure & Platform").
                // Fix: scope to the same <li> as the title element, so we only check
                // the most recent role. If no location there → header fallback below.
                if (titleEl) {
                    const roleEntry = titleEl.closest('li');
                    if (roleEntry) {
                        const locEl = roleEntry.querySelector(
                            '[data-test-grouped-position-entity-location] [data-test-text-highlighter-text-only], '
                            + '[data-test-position-entity-location] [data-test-text-highlighter-text-only]'
                        );
                        if (locEl) {
                            result.location = locEl.textContent.trim();
                            result.debug.push(`Location (experience, first role): "${result.location}"`);
                        } else {
                            const locDd = roleEntry.querySelector(
                                '[data-test-grouped-position-entity-location], [data-test-position-entity-location]'
                            );
                            if (locDd) {
                                result.location = locDd.textContent.trim();
                                result.debug.push(`Location (experience dd, first role): "${result.location}"`);
                            }
                        }
                    }
                }

                // ── Fallbacks: Panel header lockup ─────────────────
                if (!result.title) {
                    const headlineEl = document.querySelector('[data-test-row-lockup-headline]');
                    if (headlineEl) {
                        result.title = cleanText(headlineEl);
                        result.debug.push(`Title (headline fallback): "${result.title}"`);
                    }
                }

                if (!result.company) {
                    const employerEl = document.querySelector(
                        '[data-test-topcard-condensed-lockup-current-employer]'
                    );
                    if (employerEl) {
                        result.company = cleanText(employerEl);
                        result.debug.push(`Company (header fallback): "${result.company}"`);
                    }
                }

                if (!result.location) {
                    const locHeader = document.querySelector('[data-test-row-lockup-location]');
                    if (locHeader) {
                        // Header location has a leading "·" — strip it
                        result.location = cleanText(locHeader).replace(/^[·•\s]+/, '').trim();
                        result.debug.push(`Location (header fallback): "${result.location}"`);
                    }
                }

                return result;
            }
        """)

        name = panel_data.get("name", "").strip()
        current_title = panel_data.get("title", "").strip()
        current_company = panel_data.get("company", "").strip()
        location = panel_data.get("location", "").strip()

        for msg in panel_data.get("debug", []):
            logger.debug(f"      {msg}")

        if not name:
            logger.warning("    Could not find candidate name in panel")
            await page.screenshot(path="output/debug_panel_extraction.png")
            return None

        # Skip out-of-network candidates
        if name == "LinkedIn Member":
            logger.debug("    Skipping out-of-network candidate")
            return None

        logger.debug(f"    Title='{current_title}', Company='{current_company}', Location='{location}'")

        # ── 1. Education check (first filter) ────────────────────
        should_scrape, review_note, grad_year = await _extract_education_from_panel(page)
        if not should_scrape:
            logger.debug(f"    Skipping '{name}' — education out of range or no relevant degree")
            return None

        # ── 2. Title whitelist / blacklist check (before slow URL extraction) ─
        title_review = ""
        if title_whitelist is not None and current_title:
            from filters import title_matches_whitelist
            title_passes, title_review = title_matches_whitelist(current_title, title_whitelist)
            if not title_passes:
                logger.debug(f"    Skipping '{name}' — title '{current_title}' blacklisted or not in whitelist")
                return None
        elif title_whitelist is not None and not current_title:
            logger.debug(f"    No title extracted for '{name}' — allowing through (title unknown)")

        # Merge education + title review notes
        if title_review:
            review_note = f"{review_note}; {title_review}".strip("; ") if review_note else title_review

        # ── 3. Public LinkedIn URL (expensive — only reached if above pass) ──
        public_url = await _get_public_url_from_panel(page)

        from datetime import datetime
        current_year = datetime.now().year
        years_exp = (current_year - grad_year) if grad_year else None

        if review_note:
            logger.debug(f"    Review flag for '{name}': {review_note}")

        return {
            "full_name": name,
            "current_company": current_company,
            "current_title": current_title,
            "linkedin_public_url": public_url,
            "location": normalize_location(location),
            "headline": f"{current_title} at {current_company}" if current_title and current_company else current_title or current_company,
            "bachelors_grad_year": grad_year,
            "years_experience": years_exp,
            "recruiter_url": "",
            "needs_review": bool(review_note),
            "review": review_note,
        }

    except Exception as e:
        logger.warning(f"    Error extracting from panel: {e}")
        return None


async def _get_public_url_from_panel(page: Page) -> str:
    """
    Extract public LinkedIn URL by clicking the "Public profile" button in the panel.
    """
    try:
        public_button = await page.query_selector(
            'button[data-test-public-profile-trigger], '
            'button:has-text("Public profile")'
        )

        if public_button:
            logger.debug("    Clicking 'Public profile' button...")
            await public_button.click()
            await random_sleep(1, 2)

            profile_link = await page.query_selector(
                'a[data-test-public-profile-link], '
                'a:has-text("Open profile in new tab")'
            )

            if profile_link:
                url = await profile_link.get_attribute("href")
                await page.keyboard.press("Escape")
                await random_sleep(0.5, 1)
                if url:
                    return _normalize_url(url)
            else:
                logger.debug("    Could not find profile link in popover")
                await page.keyboard.press("Escape")

        # Fallback: scan for /in/ URLs in the page
        url = await page.evaluate("""
            () => {
                for (const a of document.querySelectorAll('a[href*="linkedin.com/in/"]')) {
                    const href = a.getAttribute('href');
                    if (href) return href;
                }
                return null;
            }
        """)
        if url:
            return _normalize_url(url)

    except Exception as e:
        logger.debug(f"    Error getting public URL: {e}")

    return ""


def _classify_education(entries: list, has_education: bool) -> tuple:
    """
    Classify education entries and decide whether to scrape.

    Returns (should_scrape: bool, review_note: str, grad_year: int | None)

    Decision table:
      - No education section          → scrape, review="no education"
      - Bachelor found, year 2010-24  → scrape, review=""
      - Bachelor found, year outside  → skip
      - Multiple bachelors            → scrape, review="multi bachelor - review"
      - No bachelor + has master      → scrape, review="No bachelor's - review"
      - No bachelor, no master        → skip
      - Bachelor, no year found       → scrape, review="no edu year - review"
    """
    BACHELOR_RE = re.compile(
        r'\bbachelor|\bbs\b|\bba\b|b\.s\b|b\.a\b|b\.sc\b|b\.eng\b|b\.e\b|btech\b|b\.tech\b',
        re.IGNORECASE
    )
    MASTER_RE = re.compile(
        r'\bmaster|\bmba\b|m\.b\.a\b|m\.s\b|m\.a\b|m\.eng\b|m\.sc\b|mtech\b|m\.tech\b',
        re.IGNORECASE
    )

    if not has_education:
        return True, "no education", None

    bachelors = [e for e in entries if BACHELOR_RE.search(e.get('degree', ''))]
    has_master = any(MASTER_RE.search(e.get('degree', '')) for e in entries)

    if len(bachelors) == 0:
        if has_master:
            return True, "No bachelor's - review", None
        return False, "", None  # no relevant degree → skip

    if len(bachelors) > 1:
        return True, "multi bachelor - review", None

    # Single bachelor
    grad_year = bachelors[0].get('year')
    if grad_year is None:
        return True, "no edu year - review", None

    if 2010 <= grad_year <= 2024:
        return True, "", grad_year
    else:
        return False, "", grad_year  # out of range → skip


async def _extract_education_from_panel(page: Page) -> tuple:
    """
    Extract education entries from the open profile panel using confirmed
    data-test-* selectors from HTML inspection.

    Selectors used:
      li[data-live-test-education-item]                    — each education row
      [data-test-education-entity-degree-name]
        span[data-test-text-highlighter-text-only]         — degree name text
      [data-test-education-entity-dates] time (last)       — grad year
        (year ranges like 2013–2017 use two <time> elements; we take the last)

    Returns (should_scrape: bool, review_note: str, grad_year: int | None)
    """
    try:
        edu_data = await page.evaluate(r"""
            () => {
                const result = { entries: [], hasEducation: false, hasShowMore: false };
                const items = document.querySelectorAll('li[data-live-test-education-item]');
                if (items.length === 0) return result;
                result.hasEducation = true;

                // If a "See more education" button exists, the list is truncated.
                // These candidates almost always have too many degrees and fall outside
                // our grad year range — skip them immediately.
                const showMoreBtn = document.querySelector(
                    '[data-test-education-card-expand-more-lower-button]'
                );
                if (showMoreBtn) {
                    result.hasShowMore = true;
                    return result;
                }

                for (const item of items) {
                    // Degree name
                    const degreeEl = item.querySelector(
                        '[data-test-education-entity-degree-name] span[data-test-text-highlighter-text-only]'
                    );
                    const degree = degreeEl ? degreeEl.textContent.trim() : '';

                    // Grad year: find all <time> elements in the dates cell, take the last
                    const datesCell = item.querySelector('[data-test-education-entity-dates]');
                    let year = null;
                    if (datesCell) {
                        const times = datesCell.querySelectorAll('time');
                        if (times.length > 0) {
                            const txt = times[times.length - 1].textContent.trim();
                            const m = txt.match(/\d{4}/);
                            if (m) year = parseInt(m[0]);
                        }
                    }

                    result.entries.push({ degree: degree, year: year });
                }
                return result;
            }
        """)

        if edu_data.get('hasShowMore'):
            logger.debug("    Education 'Show more' button found — skipping (likely too old)")
            return False, "", None

        entries = edu_data.get('entries', [])
        has_education = edu_data.get('hasEducation', False)

        logger.debug(f"    Education entries: {entries}")
        return _classify_education(entries, has_education)

    except Exception as e:
        logger.debug(f"    Error extracting education: {e}")
        # On error, allow through with a review flag
        return True, "no education", None


def _normalize_url(url: str) -> str:
    match = re.search(r'linkedin\.com/in/([\w-]+)', url)
    if match:
        return f"https://www.linkedin.com/in/{match.group(1)}"
    return url


async def _click_next_candidate(page: Page) -> bool:
    """
    Click the "Next candidate" arrow in the profile panel.
    Returns True if clicked, False if we're on the last candidate.

    Selector confirmed from HTML: a[data-test-pagination-next]
    (distinct from a[data-test-mini-pagination-next] which is the search page pager)
    """
    try:
        next_btn = await page.query_selector(
            'a[data-test-pagination-next], '
            'a[rel="next"].skyline-pagination-link'
        )

        if not next_btn:
            logger.debug("    No Next candidate button found — last candidate")
            return False

        aria_hidden = await next_btn.get_attribute("aria-hidden")
        if aria_hidden == "true":
            logger.debug("    Next button is hidden — last candidate")
            return False

        aria_disabled = await next_btn.get_attribute("aria-disabled")
        if aria_disabled == "true":
            logger.debug("    Next button is disabled — last candidate")
            return False

        await next_btn.click()
        logger.debug("    ✓ Clicked Next candidate")
        await random_sleep(1, 2)
        return True

    except Exception as e:
        logger.debug(f"    Error clicking Next: {e}")
        return False


async def _close_profile_panel(page: Page):
    """Close the profile panel to return to search results."""
    try:
        await page.keyboard.press("Escape")
        await random_sleep(0.5, 1)

        close_btn = await page.query_selector(
            'button[aria-label="Close"], '
            'button[aria-label="Dismiss"], '
            'button[class*="close"], '
            '[class*="artdeco-dismiss"]'
        )
        if close_btn:
            try:
                await close_btn.click(timeout=2000)
            except Exception:
                pass
    except Exception:
        pass
