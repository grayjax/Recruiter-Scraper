"""
main.py — Entry point.

Key changes from v1:
- Incremental save (crash recovery)
- Deduplication via seen_urls set
- Daily cap (max_profiles_per_run)
- Grad year extraction attempted from search card FIRST
- Profile panel opened only when needed
- Interactive CLI prompts for search URL and page range
"""
import asyncio
import json
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
from datetime import datetime

from browser import init_browser, login_to_linkedin
from search import run_search, load_incremental_profiles
from filters import apply_filters, load_title_whitelist
from export import write_csv, push_to_airtable

load_dotenv()

CHECKPOINT_FILE = "output/_checkpoint.jsonl"


def get_user_input(config: dict) -> dict:
    """
    Prompt user for search parameters interactively.
    Returns updated config with user input.
    """
    print("\n" + "="*60)
    print("LinkedIn Recruiter Lite Automation")
    print("="*60 + "\n")

    # Get search URL
    default_url = config["search"].get("saved_search_url", "")
    if default_url and default_url != "https://www.linkedin.com/recruiter/search/...":
        print(f"Current search URL (from config.yaml):")
        print(f"  {default_url[:80]}...")
        use_default = input("\nUse this URL? (y/n, default=y): ").strip().lower()
        if use_default in ["", "y", "yes"]:
            search_url = default_url
        else:
            search_url = input("\nPaste your LinkedIn Recruiter search URL: ").strip()
    else:
        print("Paste your LinkedIn Recruiter search URL below.")
        print("(Tip: Run your search with filters in Recruiter Lite, then copy the URL)")
        search_url = input("\nSearch URL: ").strip()

    config["search"]["saved_search_url"] = search_url

    # Get starting page
    print("\n" + "-"*60)
    start_page = input("Start from page number (default=1): ").strip()
    start_page = int(start_page) if start_page.isdigit() else 1
    config["search"]["start_page"] = start_page

    # Get max pages
    default_max = config["search"].get("max_pages", 10)
    print("\nHow many pages to scrape?")
    print("  - Enter a number (e.g., 10)")
    print("  - Enter 'all' to scrape until search is complete")
    max_pages_input = input(f"Pages to scrape (default={default_max}): ").strip().lower()

    if max_pages_input in ["all", "a", ""]:
        if max_pages_input == "":
            max_pages = default_max
            scrape_all = False
        else:
            max_pages = 9999  # Large number to ensure we get all pages
            scrape_all = True
    elif max_pages_input.isdigit():
        max_pages = int(max_pages_input)
        scrape_all = False
    else:
        max_pages = default_max
        scrape_all = False

    # Calculate ending page (max_pages is the COUNT of pages to scrape)
    if scrape_all:
        end_page = 9999
        config["search"]["max_pages"] = end_page
    else:
        end_page = start_page + max_pages - 1
        config["search"]["max_pages"] = end_page

    config["search"]["scrape_all"] = scrape_all

    # Display summary
    if scrape_all:
        print("\n" + "-"*60)
        print(f"📊 Summary:")
        print(f"   Starting page: {start_page}")
        print(f"   Ending page: ALL (until search complete)")
        print(f"   Estimated profiles: Unknown (will scrape all)")
        print("-"*60)
    else:
        estimated_profiles = max_pages * 25
        print("\n" + "-"*60)
        print(f"📊 Summary:")
        print(f"   Starting page: {start_page}")
        print(f"   Ending page: {end_page}")
        print(f"   Total pages: {max_pages}")
        print(f"   Estimated profiles: ~{estimated_profiles}")
        print("-"*60)

    confirm = input("\nProceed? (y/n, default=y): ").strip().lower()
    if confirm in ["n", "no"]:
        print("\nExiting...")
        exit(0)

    print("\n" + "="*60 + "\n")
    return config


def load_checkpoint() -> set:
    """Load already-processed recruiter URLs from checkpoint."""
    seen = set()
    path = Path(CHECKPOINT_FILE)
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                record = json.loads(line)
                seen.add(record.get("recruiter_url", ""))
            except json.JSONDecodeError:
                continue
    return seen


def append_checkpoint(profile: dict):
    """Append one profile to the checkpoint file (crash recovery)."""
    Path(CHECKPOINT_FILE).parent.mkdir(exist_ok=True)
    with open(CHECKPOINT_FILE, "a") as f:
        f.write(json.dumps(profile) + "\n")


async def main():
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    # ── Interactive prompts ────────────────────────────────
    config = get_user_input(config)

    logger.info("Starting...")

    # ── Load title whitelist (optional) ───────────────────────────
    title_whitelist = load_title_whitelist()
    if title_whitelist is None:
        logger.info("No job_titles_whitelist.txt found — all titles will be collected")
    else:
        logger.info(f"Title whitelist active: {len(title_whitelist)} unique phrases loaded")

    browser = None
    all_profiles = []
    last_page_scraped = 1

    try:
        # ── 1. Browser + login ─────────────────────────────────
        browser, context, page = await init_browser(config["browser"])
        await login_to_linkedin(page, config["browser"])

        # ── 2. Run search and extract profiles ────────────────
        logger.info("Processing search results via panel navigation...")
        all_profiles, last_page_scraped = await run_search(page, config["search"], title_whitelist)
        logger.info(f"Extracted {len(all_profiles)} profiles.")

        # ── 3. Save to checkpoint ──────────────────────────────
        for profile in all_profiles:
            append_checkpoint(profile)

    except KeyboardInterrupt:
        logger.warning("\n⚠ Stopped by user - saving partial results...")

    finally:
        # ── 4. Filter ──────────────────────────────────────────
        # If all_profiles is empty (e.g., Ctrl+C during panel close),
        # fall back to the incrementally saved file
        if not all_profiles:
            recovered = load_incremental_profiles()
            if recovered:
                logger.info(f"  Recovered {len(recovered)} profiles from incremental save")
                all_profiles = recovered

        if all_profiles:
            filtered = apply_filters(all_profiles, config["filters"])
            logger.info(f"{len(filtered)} profiles after grad year filter.")

            # ── 5. Export ──────────────────────────────────────────
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = None

            if config["output"]["csv"]["enabled"]:
                fname = config["output"]["csv"]["filename"].replace(
                    "{timestamp}", timestamp
                )
                write_csv(filtered, f"output/{fname}")

            if config["output"]["airtable"]["enabled"]:
                push_to_airtable(filtered, config["output"]["airtable"])

            # ── 6. Summary ─────────────────────────────────────────
            print("\n" + "="*60)
            print("✅ RESULTS SAVED")
            print("="*60)
            print(f"📊 Results:")
            print(f"   - Profiles extracted: {len(all_profiles)}")
            print(f"   - After filtering: {len(filtered)}")
            print(f"   - Last page scraped: {last_page_scraped}")
            print()
            print(f"📁 Output:")
            if config["output"]["csv"]["enabled"] and fname:
                print(f"   - CSV file: output/{fname}")
            if config["output"]["airtable"]["enabled"]:
                print(f"   - Pushed to Airtable ✓")
            print()
            print(f"🔄 To resume from where you left off:")
            print(f"   - Start from page: {last_page_scraped + 1}")
            print("="*60 + "\n")

            logger.success(f"Done. {len(filtered)} candidates exported.")
        else:
            logger.warning("No profiles collected.")

        # ── 7. Cleanup ─────────────────────────────────────────
        if browser:
            await browser.close()


if __name__ == "__main__":
    # Windows uses ProactorEventLoopPolicy by default (Python 3.8+)
    # which supports subprocesses (required for Playwright)
    # We handle cleanup errors separately below

    import warnings
    # Suppress specific Windows asyncio cleanup warnings
    warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed transport")

    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            # Ignore this error - it's a known Windows cleanup issue
            pass
        else:
            raise
    except KeyboardInterrupt:
        logger.info("\nStopped by user.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise
