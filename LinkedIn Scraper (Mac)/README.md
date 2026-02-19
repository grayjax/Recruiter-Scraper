# LinkedIn Recruiter Scraper — Mac User Guide

## What This Tool Does

Automatically pulls candidate profiles from a LinkedIn Recruiter Lite search and saves them to a CSV file. It filters by graduation year (2010–2024) and job title, so only relevant candidates land in your spreadsheet.

---

## Requirements

- **Mac** running macOS 10.15 (Catalina) or newer
- **Google Chrome** installed (download from [google.com/chrome](https://www.google.com/chrome/))
- **Python 3** installed (download from [python.org/downloads](https://www.python.org/downloads/) if needed)
- A **LinkedIn Recruiter Lite** account

---

## First-Time Setup (One Time Only)

1. Unzip the `LinkedIn Scraper (Mac)` folder you received
2. Move it somewhere permanent (Desktop or Documents — just don't move it after setup)
3. **Right-click** `setup_mac.sh` → click **Open** → click **Open** again when macOS warns you
4. A Terminal window will open and install everything automatically (~2 minutes)
5. When it says "Setup complete!", close the Terminal window

> **Why right-click → Open?** macOS blocks double-clicking scripts from the internet the first time. Right-click → Open bypasses this one-time warning.

---

## How to Run a Search

### Step 1 — Launch the App

**Right-click** `Launch Scraper.command` → **Open** → **Open**

> After the first time, you can double-click it directly.

A window titled "LinkedIn Recruiter Scraper" will appear with three tabs.

---

### Step 2 — Setup Tab: Launch Chrome

1. Click **"Launch Chrome"**
   - A Chrome window opens automatically
   - *(If Chrome isn't found, open it manually — see [Troubleshooting](#troubleshooting))*
2. In that Chrome window:
   - Go to **linkedin.com/recruiter**
   - Log in to your Recruiter Lite account
   - Wait for the Recruiter dashboard to load
3. Click **"Continue to Search →"** in the app

> **Important:** Use only the Chrome window the app opened — not your regular Chrome.

---

### Step 3 — Search Tab: Configure Your Search

1. **Run your search on LinkedIn first** — apply all filters, then wait for results
2. **Copy the full URL** from the address bar
3. **Paste it** into the Search URL box
4. **Set the page range** (each page ≈ 25 profiles)
5. **Choose where to save** — defaults to your Desktop
6. Click **"Start Scraping →"**

---

### Step 4 — Run Tab: Watch It Work

The app shows a live activity log. Do not click in the Chrome window while it runs.

When done:
- Status shows **"Done! X profiles saved."**
- Click **"Open Output Folder"** to find your CSV

---

## Understanding Your CSV

| Column | What It Contains |
|--------|-----------------|
| `full_name` | Candidate's name |
| `current_company` | Current employer |
| `current_title` | Current job title |
| `linkedin_public_url` | Their LinkedIn profile link |
| `location` | City / region |
| `review` | Flag for manual review (see below) |
| `bachelors_grad_year` | Detected graduation year |
| `years_experience` | Years since graduation |

### The "Review" Column

| Note | Meaning |
|------|---------|
| `no education` | No education section found — likely fine |
| `no edu year` | Has Bachelor's but no graduation year listed |
| `No bachelor's - review` | Has Master's but no Bachelor's detected |
| `multi bachelor - review` | Multiple bachelor's degrees — unusual |
| `title: 'head of' — review` | Senior "Head of" title — worth a quick check |

---

## Resuming a Run

LinkedIn limits daily profile views. To continue later:
1. Note the **last page scraped** from the activity log
2. Next session: start from the next page
3. Each run saves to a separate timestamped CSV — combine in Excel

---

## Troubleshooting

### "Chrome not found"
- Make sure Google Chrome is installed in your Applications folder
- If Chrome is installed but not found, open it manually and run:
  ```
  /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port=9222 \
    --user-data-dir=/tmp/chrome-li-debug
  ```
  Then skip clicking "Launch Chrome" and proceed to "Continue to Search →"

### App won't open / "cannot be opened"
- Right-click the file → Open → Open (bypasses macOS security warning)
- You only need to do this once per file

### "No module named..." error in Terminal
- Run `setup_mac.sh` again — a package may not have installed correctly

### LinkedIn shows a CAPTCHA
1. Click **Stop** in the app
2. Complete the CAPTCHA in Chrome manually
3. Click **Run Again** and resume from the last page

---

## What Gets Filtered Out

**Education:** Must have Bachelor's degree, graduation year 2010–2024

**Titles excluded:** Director, VP, Vice President, Developer Advocate, Operations roles, Merchandising, Professional Services
