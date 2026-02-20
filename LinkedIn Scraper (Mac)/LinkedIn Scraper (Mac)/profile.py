"""
profile.py — Open the profile slide-over panel and extract detailed data.

CRITICAL OBSERVATIONS FROM SCREENSHOTS:

1. Profile opens as a PANEL (slide-over) when you click the name link
   on the search results page. It does NOT navigate to a new URL.
   The panel loads on top of the search results.

2. Profile header shows:
   - Name (h1/h2)
   - Headline: "Senior Software Engineer at Etsy"
   - Sub-line: "Etsy · Drexel University · Brooklyn, New York, United States · Software Development · 273"
   - "Public profile" link (small icon + text)

3. "Public profile" click reveals a small popover with:
   - "Open profile in new tab" (this is an <a> with the actual public URL!)
   - "Copy link"
   We grab the href from "Open profile in new tab" — no clipboard needed.

4. Education section (Image 3) shows:
   - School name + logo
   - "Bachelor of Science (BS) · Computer Science"
   - "2012 – 2017"
   - Concentration line (optional)
"""
import re
from playwright.async_api import Page
from utils import random_sleep, normalize_location
from loguru import logger


# ── Bachelor's degree keywords ────────────────────────────────
BACHELORS_KW = [
    "bachelor", "b.s.", "b.s", "b.a.", "b.a", "b.sc", "b.eng",
    "b.e.", "btech", "b.tech", "(bs)", "(ba)", "bs ", "ba ",
]


async def open_profile_and_extract(page: Page, stub: dict) -> dict | None:
    """
    Click the candidate's name on the search results page to open
    the profile panel, then extract all fields.
    """
    try:
        # ── Step 1: Try to extract grad year from search card first ──
        card_grad_year = _parse_bachelors_year_from_text(stub.get("education_text", ""))

        # ── Step 2: Click the name link to open the profile panel ────
        # We need the profile panel for: public URL, and education
        # details if the card didn't have enough info.

        # Find and click the name link matching this stub
        # Try multiple strategies to find the link
        name_link = None

        # Strategy 1: Match by partial href (in case of query params or relative URLs)
        recruiter_id = stub["recruiter_url"].split("/talent/profile/")[-1].split("?")[0]
        name_link = await page.query_selector(f'a[href*="/talent/profile/{recruiter_id}"]')

        if not name_link:
            # Strategy 2: Find by exact text match
            # Escape quotes in name for selector
            escaped_name = stub["name"].replace('"', '\\"')
            try:
                name_link = await page.query_selector(f'a:has-text("{escaped_name}")')
            except Exception:
                pass

        if not name_link:
            # Strategy 3: Use page.evaluate to find all profile links and match
            logger.debug(f"  Trying JavaScript search for {stub['name']}...")
            link_found = await page.evaluate("""
                (targetName) => {
                    const links = document.querySelectorAll('a[href*="/talent/profile/"]');
                    console.log('Found', links.length, 'profile links');
                    for (const link of links) {
                        const linkText = link.textContent.trim();
                        console.log('  Link text:', linkText);
                        if (linkText === targetName || linkText.includes(targetName)) {
                            link.setAttribute('data-target-link', 'true');
                            return true;
                        }
                    }
                    return false;
                }
            """, stub["name"])

            if link_found:
                name_link = await page.query_selector('a[data-target-link="true"]')

        if not name_link:
            # Debug: take screenshot and log available links
            screenshot_path = f"output/debug_profile_{stub['name'].replace(' ', '_')}.png"
            await page.screenshot(path=screenshot_path)

            # Log what links we can actually see
            available_links = await page.evaluate("""
                () => {
                    const links = document.querySelectorAll('a[href*="/talent/profile/"]');
                    return Array.from(links).slice(0, 5).map(l => ({
                        text: l.textContent.trim(),
                        href: l.getAttribute('href')
                    }));
                }
            """)
            logger.warning(f"  Could not find link for {stub['name']}")
            logger.debug(f"  Screenshot saved to {screenshot_path}")
            logger.debug(f"  Available links on page: {available_links}")
            return None

        logger.debug(f"  Found link for {stub['name']}, scrolling into view...")
        # Scroll the link into view before clicking
        await name_link.scroll_into_view_if_needed()
        await random_sleep(0.5, 1)

        logger.debug(f"  Clicking link...")
        await name_link.click()
        await random_sleep(3, 4)  # Wait longer for panel to fully load

        # Wait for the profile panel to appear
        # The panel typically has a recognizable container
        panel_opened = False
        try:
            # Try multiple selectors for the profile panel
            await page.wait_for_selector(
                '[class*="profile-drawer"], '
                '[class*="profile-panel"], '
                '[class*="profile-topcard"], '
                '[class*="slideup"], '
                '[class*="detail-panel"], '
                'section[class*="profile"], '
                'div[role="dialog"]',
                timeout=10000
            )
            panel_opened = True
            logger.debug("  Profile panel opened")
        except Exception as e:
            logger.warning(f"  Profile panel did not open for {stub['name']}: {e}")
            # Take screenshot to debug
            screenshot_path = f"output/debug_panel_failed_{stub['name'].replace(' ', '_')}.png"
            await page.screenshot(path=screenshot_path)
            logger.debug(f"  Screenshot saved to {screenshot_path}")
            return None

        await random_sleep(2, 3)  # Give panel time to fully load content

        # ── Step 3: Extract public LinkedIn URL ──────────────────
        public_url = await _get_public_url(page)

        # ── Step 4: Extract education from profile panel ─────────
        # Only do this if we didn't get a confident grad year from the card
        grad_year = card_grad_year
        if grad_year is None:
            grad_year = await _extract_bachelors_grad_year(page)

        # ── Step 5: Calculate years of experience ────────────────
        from datetime import datetime
        current_year = datetime.now().year
        years_exp = (current_year - grad_year) if grad_year else None

        # ── Step 6: Build the output record ──────────────────────
        # TSV format: Name | Company | Role | LinkedIn URL | Location
        profile = {
            "full_name": stub["name"],
            "current_company": stub.get("current_company", ""),
            "current_title": stub.get("current_title", ""),
            "linkedin_public_url": public_url,
            "location": normalize_location(stub.get("location", "")),
            "headline": stub.get("headline", ""),
            "bachelors_grad_year": grad_year,
            "years_experience": years_exp,
            "recruiter_url": stub["recruiter_url"],
            "needs_review": False,
        }

        # ── Step 7: Close the profile panel ──────────────────────
        await _close_profile_panel(page)
        await random_sleep(1, 2)

        return profile

    except Exception as e:
        logger.warning(f"  Failed on {stub.get('name')}: {e}")
        # Try to close panel to recover
        try:
            await _close_profile_panel(page)
        except Exception:
            pass
        return None


async def _get_public_url(page: Page) -> str:
    """
    Extract the public LinkedIn URL from the profile panel.

    Based on screenshots: There's a "Public profile" link. Clicking it shows
    a popover with "Open profile in new tab" (which has the real href)
    and "Copy link".

    Strategy:
    1. Click the "Public profile" link/button to trigger the popover
    2. Grab the href from "Open profile in new tab"
    3. Close the popover
    """
    try:
        # Wait a moment for the profile panel to fully load
        await random_sleep(1, 2)

        # Find the "Public profile" link - try multiple selectors
        public_link = None

        # Try different text variations
        for text in ["Public profile", "public profile"]:
            try:
                public_link = await page.query_selector(f'a:has-text("{text}")')
                if public_link:
                    logger.debug(f"  Found 'Public profile' link with text: {text}")
                    break
            except Exception:
                pass

        # If not found by text, try by class/attribute patterns
        if not public_link:
            public_link = await page.query_selector(
                'a[class*="public-profile"], '
                'button[class*="public-profile"], '
                '[data-test-public-profile]'
            )

        if public_link:
            logger.debug("  Clicking 'Public profile' link...")
            await public_link.click()
            await random_sleep(1, 2)  # Wait for popover to appear

            # Now look for "Open profile in new tab" in the popover
            open_tab_link = None
            for text in ["Open profile in new tab", "open profile in new tab"]:
                try:
                    open_tab_link = await page.query_selector(f'a:has-text("{text}")')
                    if open_tab_link:
                        logger.debug(f"  Found popup link with text: {text}")
                        break
                except Exception:
                    pass

            if open_tab_link:
                url = await open_tab_link.get_attribute("href")
                logger.debug(f"  Extracted public URL: {url}")
                # Close the popover by pressing Escape
                await page.keyboard.press("Escape")
                await random_sleep(0.5, 1)
                if url:
                    return _normalize_url(url)
            else:
                logger.warning("  Could not find 'Open profile in new tab' link in popover")
                await page.keyboard.press("Escape")  # Close popover anyway

        # ── Fallback: scan all <a> tags for /in/ URLs ────────
        url = await page.evaluate("""
            () => {
                const anchors = document.querySelectorAll('a[href*="/in/"]');
                for (const a of anchors) {
                    const href = a.getAttribute('href');
                    if (href && href.includes('linkedin.com/in/')) {
                        return href;
                    }
                }
                return null;
            }
        """)
        if url:
            return _normalize_url(url)

        # ── Fallback 2: regex the entire page HTML ───────────
        html = await page.content()
        match = re.search(
            r'https?://(?:www\.)?linkedin\.com/in/([\w-]+)', html
        )
        if match:
            return f"https://www.linkedin.com/in/{match.group(1)}"

    except Exception as e:
        logger.debug(f"  Public URL extraction error: {e}")

    return ""


async def _extract_bachelors_grad_year(page: Page) -> int | None:
    """
    Extract Bachelor's degree graduation year from the profile panel.

    From Image 3, the Education section looks like:

        Drexel University
        Bachelor of Science (BS) · Computer Science
        2012 – 2017
        Concentration in Data Structures/Algorithms and Numerical Analysis

    We need to:
    1. Find all education entries
    2. Identify which one is a Bachelor's degree
    3. Extract the END year (graduation year, not start year)

    IMPORTANT: Ignore Master's, MBA, Associate's, PhD, bootcamps, high school.
    """
    education_entries = await page.evaluate("""
        () => {
            const entries = [];

            // The education section in Recruiter Lite profile panel
            // Look for the "Education" heading and then its sibling entries
            const allText = document.body.innerText;
            const eduMatch = allText.match(/Education[\\s\\S]*?(?=Skills|$)/);

            // Alternative: find education items by structure
            const eduItems = document.querySelectorAll(
                '[class*="education"] [class*="entity"], ' +
                '[class*="education"] [class*="item"], ' +
                '[class*="education"] li, ' +
                'section:has(> h2:contains("Education")) li'
            );

            // If structured items found, parse them
            if (eduItems.length > 0) {
                for (const item of eduItems) {
                    entries.push(item.textContent.trim());
                }
            }

            // Also try: find all text blocks near "Education" heading
            const headings = document.querySelectorAll('h2, h3, [class*="section-title"]');
            for (const h of headings) {
                if (h.textContent.trim().toLowerCase().includes('education')) {
                    // Get the parent section
                    let section = h.closest('section') || h.parentElement;
                    if (section) {
                        const items = section.querySelectorAll(
                            'li, [class*="item"], [class*="entity"]'
                        );
                        for (const item of items) {
                            const text = item.textContent.trim();
                            if (text && !entries.includes(text)) {
                                entries.push(text);
                            }
                        }
                        // If no sub-items, grab the whole section text
                        if (entries.length === 0) {
                            entries.push(section.textContent.trim());
                        }
                    }
                }
            }

            return entries;
        }
    """)

    # Parse each entry looking for a Bachelor's degree
    for entry_text in education_entries:
        year = _parse_bachelors_year_from_text(entry_text)
        if year is not None:
            return year

    return None


def _parse_bachelors_year_from_text(text: str) -> int | None:
    """
    Given a block of education text, find a Bachelor's degree
    and return its graduation year.

    Examples it should handle:
    - "Drexel University, Bachelor of Science (BS) · 2012 – 2017"  → 2017
    - "University of Tasmania, Bachelor of Science/Bachelor of Laws (BSc LLB) · 2005 – 2013"  → 2013
    - "Brown University, Bachelor's Degree · 2012 – 2016"  → 2016
    - "University of California, Davis, Bachelor of Science · BS · 2016 – 2020"  → 2020
    - "National Institute of Technology Rourkela, Bachelors · 2017"  → 2017

    Examples it should SKIP:
    - "Cornell University, Master of Engineering · 2011 – 2012"
    - "Stanford University · 2018"  (no degree type — ambiguous)
    - "Hack Reactor · 2020"  (bootcamp)
    - "Cherry Creek High School · 2008 – 2012"  (high school)
    """
    if not text:
        return None

    text_lower = text.lower()

    # Skip non-Bachelor's degrees
    skip_patterns = [
        "master", "m.s.", "m.s", "m.a.", "m.a", "mba", "m.b.a",
        "ph.d", "phd", "doctor", "associate", "a.s.", "a.a.",
        "high school", "diploma", "certificate", "bootcamp",
        "hack reactor", "app academy", "flatiron", "general assembly",
        "graddip", "postgrad",
    ]
    for skip in skip_patterns:
        if skip in text_lower:
            return None

    # Check if any bachelor's keyword is present
    has_bachelors = any(kw in text_lower for kw in BACHELORS_KW)
    if not has_bachelors:
        return None

    # Extract all 4-digit years
    years = re.findall(r'\b(19|20)\d{2}\b', text)
    if years:
        # Last year in the range = graduation year
        return int(years[-1])

    return None


def _normalize_url(url: str) -> str:
    """Normalize a LinkedIn public URL."""
    match = re.search(r'linkedin\.com/in/([\w-]+)', url)
    if match:
        return f"https://www.linkedin.com/in/{match.group(1)}"
    return url


async def _close_profile_panel(page: Page):
    """Close the profile slide-over panel to return to search results."""
    try:
        # Look for an X / close button on the panel
        # The X button is typically in the top right of the panel
        close_btn = await page.query_selector(
            'button[aria-label="Close"], '
            'button[aria-label="Dismiss"], '
            'button[class*="close"], '
            'button[class*="dismiss"], '
            '[class*="artdeco-dismiss"], '
            '[data-test-modal-close], '
            'button[type="button"]:has(svg[class*="close"]), '
            'button:has(svg[data-test-icon="close-medium"])'
        )
        if close_btn:
            logger.debug("  Closing profile panel...")
            await close_btn.click()
            await random_sleep(1, 2)
            return

        # Fallback: press Escape
        logger.debug("  Closing panel with Escape key...")
        await page.keyboard.press("Escape")
        await random_sleep(1, 2)
    except Exception as e:
        logger.debug(f"  Error closing panel: {e}")
        # Try Escape as last resort
        try:
            await page.keyboard.press("Escape")
            await random_sleep(1, 2)
        except Exception:
            pass
