"""
browser.py — Playwright browser with session persistence.

Login is MANUAL — the script opens a browser, waits for you to log in,
then saves cookies for subsequent runs.
"""
import os
from playwright.async_api import async_playwright
from utils import random_sleep
from loguru import logger

COOKIE_PATH = "cookies/linkedin_session.json"


async def init_browser(browser_config: dict):
    """
    Launch or connect to browser.

    If use_existing_browser=true, connects to an existing Chrome/Edge instance
    running with remote debugging enabled. Otherwise launches a new browser.
    """
    pw = await async_playwright().start()

    use_existing = browser_config.get("use_existing_browser", False)

    if use_existing:
        # Connect to existing browser via CDP
        cdp_url = browser_config.get("cdp_url", "http://localhost:9222")
        logger.info(f"Connecting to existing browser at {cdp_url}...")

        try:
            browser = await pw.chromium.connect_over_cdp(cdp_url)

            # Use the existing context (don't create a new one)
            contexts = browser.contexts
            if contexts:
                context = contexts[0]
                logger.success("Connected to existing browser context!")
            else:
                logger.warning("No existing contexts found, creating new one...")
                context = await browser.new_context()

            # Get the first page or create one
            pages = context.pages
            if pages:
                page = pages[0]
            else:
                page = await context.new_page()

            return browser, context, page

        except Exception as e:
            logger.error(f"Could not connect to existing browser: {e}")
            logger.error("Make sure Chrome/Edge is running with: --remote-debugging-port=9222")
            raise

    else:
        # Launch new browser (original behavior)
        browser = await pw.chromium.launch(
            headless=browser_config.get("headless", False),
            slow_mo=browser_config.get("slow_mo", 600),
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context_opts = {
            "viewport": {"width": 1440, "height": 900},
            "locale": "en-US",
        }

        # Restore saved session if available
        if browser_config.get("persist_session") and os.path.exists(COOKIE_PATH):
            try:
                import json
                with open(COOKIE_PATH) as f:
                    session_data = json.load(f)
                    num_cookies = len(session_data.get("cookies", []))
                    logger.info(f"Loading saved session ({num_cookies} cookies)...")
                context_opts["storage_state"] = COOKIE_PATH
            except Exception as e:
                logger.warning(f"Could not load session: {e}")

        context = await browser.new_context(**context_opts)

        # Mask webdriver flag
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)

        page = await context.new_page()
        return browser, context, page


async def login_to_linkedin(page, browser_config: dict):
    """Navigate to Recruiter Lite. If not logged in, wait for manual login."""
    use_existing = browser_config.get("use_existing_browser", False)

    if use_existing:
        # When using existing browser, user is already navigated
        logger.info(f"Using existing browser session at: {page.url}")
        # Don't navigate - let user stay on their current page
        await random_sleep(1, 2)
        return

    # Only navigate if launching new browser
    # Try /talent first (newer interface), fallback to /recruiter
    try:
        await page.goto(
            "https://www.linkedin.com/talent",
            wait_until="domcontentloaded",
            timeout=10000
        )
    except Exception:
        logger.debug("Could not reach /talent, trying /recruiter...")
        await page.goto(
            "https://www.linkedin.com/recruiter",
            wait_until="domcontentloaded"
        )

    await random_sleep(2, 3)
    logger.info(f"Current URL: {page.url}")

    # Check if we landed on a login page
    if "/login" in page.url or "/uas/" in page.url or "/checkpoint" in page.url:
        logger.warning("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.warning("  Not logged in!")
        logger.warning("  Please log in manually in the browser window.")
        logger.warning("  You have 5 minutes before timeout.")
        logger.warning("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # Wait until URL contains /recruiter or /talent (i.e., successful login)
        # Pattern matches both /recruiter/** and /talent/** paths
        try:
            await page.wait_for_url(
                lambda url: ("/recruiter" in url or "/talent" in url) and "/login" not in url,
                timeout=300_000  # 5 minutes
            )
        except Exception:
            # Fallback: check if already logged in
            if "/recruiter" in page.url or "/talent" in page.url:
                pass
            else:
                raise

        logger.success("Login detected!")
        await random_sleep(2, 3)
    else:
        logger.success(f"Already logged in! (URL: {page.url})")

    # Save session for next run
    if browser_config.get("persist_session"):
        os.makedirs("cookies", exist_ok=True)
        await page.context.storage_state(path=COOKIE_PATH)

        # Verify session was saved
        import json
        with open(COOKIE_PATH) as f:
            session_data = json.load(f)
            num_cookies = len(session_data.get("cookies", []))
        logger.info(f"Session saved! ({num_cookies} cookies → {COOKIE_PATH})")
